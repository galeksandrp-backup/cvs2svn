# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2006 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs, available at http://cvs2svn.tigris.org/.
# ====================================================================

"""This module contains the SVNCommitCreator class."""


import time

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.symbol import Branch
from cvs2svn_lib.database import Database
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.changeset import OrderedChangeset
from cvs2svn_lib.changeset import BranchChangeset
from cvs2svn_lib.changeset import TagChangeset
from cvs2svn_lib.svn_commit import SVNCommit
from cvs2svn_lib.svn_commit import SVNPrimaryCommit
from cvs2svn_lib.svn_commit import SVNSymbolCommit
from cvs2svn_lib.svn_commit import SVNPostCommit


class SVNCommitCreator:
  """This class coordinates the committing of changesets and symbols."""

  def __init__(self, persistence_manager):
    self._persistence_manager = persistence_manager

  def _commit(self, timestamp, cvs_revs):
    """Generates the primary SVNCommit for a set of CVSRevisions.

    CHANGES and DELETES are the CVSRevisions to be included.  Use
    TIMESTAMP as the time of the commit (do not use the timestamps
    stored in the CVSRevisions)."""

    # Lists of CVSRevisions
    changes = []
    deletes = []

    for cvs_rev in cvs_revs:
      if isinstance(cvs_rev, CVSRevisionDelete):
        deletes.append(cvs_rev)
      else:
        # CVSRevisionAdd or CVSRevisionChange:
        changes.append(cvs_rev)

    # Generate an SVNCommit unconditionally.  Even if the only change in
    # this group of CVSRevisions is a deletion of an already-deleted
    # file (that is, a CVS revision in state 'dead' whose predecessor
    # was also in state 'dead'), the conversion will still generate a
    # Subversion revision containing the log message for the second dead
    # revision, because we don't want to lose that information.
    needed_deletes = [
        cvs_rev
        for cvs_rev in deletes
        if cvs_rev.needs_delete()
        ]
    cvs_revs = changes + needed_deletes
    if cvs_revs:
      cvs_revs.sort(lambda a, b: cmp(a.cvs_file.filename, b.cvs_file.filename))
      svn_commit = SVNPrimaryCommit(cvs_revs, timestamp)

      # default_branch_cvs_revisions is a list of cvs_revs for each
      # default branch commit that will need to be copied to trunk (or
      # deleted from trunk) in a generated revision following the
      # "regular" revision.
      default_branch_cvs_revisions = [
            cvs_rev
            for cvs_rev in cvs_revs
            if cvs_rev.needs_post_commit()]

      self._persistence_manager.put_svn_commit(svn_commit)

      if not Ctx().trunk_only:
        for cvs_rev in changes + deletes:
          Ctx()._symbolings_logger.log_revision(cvs_rev, svn_commit.revnum)

        # Generate an SVNPostCommit if we have default branch revs:
        if default_branch_cvs_revisions:
          # If some of the revisions in this commit happened on a
          # non-trunk default branch, then those files have to be
          # copied into trunk manually after being changed on the
          # branch (because the RCS "default branch" appears as head,
          # i.e., trunk, in practice).  Unfortunately, Subversion
          # doesn't support copies with sources in the current txn.
          # All copies must be based in committed revisions.
          # Therefore, we generate the copies in a new revision.
          self._post_commit(
              default_branch_cvs_revisions, svn_commit.revnum, timestamp)

  def _post_commit(self, cvs_revs, motivating_revnum, timestamp):
    """Generate any SVNCommits that we can perform following CVS_REVS.

    That is, handle non-trunk default branches.  Sometimes an RCS file
    has a non-trunk default branch, so a commit on that default branch
    would be visible in a default CVS checkout of HEAD.  If we don't
    copy that commit over to Subversion's trunk, then there will be no
    Subversion tree which corresponds to that CVS checkout.  Of course,
    in order to copy the path over, we may first need to delete the
    existing trunk there."""

    cvs_revs.sort(
        lambda a, b: cmp(a.cvs_file.filename, b.cvs_file.filename)
        )
    # Generate an SVNCommit for all of our default branch cvs_revs.
    svn_commit = SVNPostCommit(motivating_revnum, cvs_revs, timestamp)
    for cvs_rev in cvs_revs:
      Ctx()._symbolings_logger.log_default_branch_closing(
          cvs_rev, svn_commit.revnum)
    self._persistence_manager.put_svn_commit(svn_commit)

  def _process_revision_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP for all of its entries.

    Creating one or more SVNCommits in the process, and store them to
    the persistence manager.  CHANGESET must be an OrderedChangeset."""

    if not changeset.cvs_item_ids:
      Log().warn('Changeset has no items: %r' % changeset)
      return

    Log().verbose('-' * 60)
    Log().verbose('CVS Revision grouping:')
    Log().verbose('  Time: %s' % time.ctime(timestamp))

    cvs_revs = list(changeset.get_cvs_items())

    if Ctx().trunk_only:
      # Filter out non-trunk revisions:
      cvs_revs = [
          cvs_rev
          for cvs_rev in cvs_revs
          if not isinstance(cvs_rev.lod, Branch)]

    self._commit(timestamp, cvs_revs)

  def close(self):
    self._done_symbols = None

  def _process_tag_changeset(self, changeset, timestamp):
    """Process TagChangeset CHANGESET, producing a SVNSymbolCommit."""

    if Ctx().trunk_only:
      return

    svn_commit = SVNSymbolCommit(
        changeset.symbol, changeset.cvs_item_ids, timestamp)
    self._persistence_manager.put_svn_commit(svn_commit)

  def _process_branch_changeset(self, changeset, timestamp):
    """Process BranchChangeset CHANGESET, producing a SVNSymbolCommit."""

    if Ctx().trunk_only:
      return

    svn_commit = SVNSymbolCommit(
        changeset.symbol, changeset.cvs_item_ids, timestamp)
    self._persistence_manager.put_svn_commit(svn_commit)
    for cvs_branch in changeset.get_cvs_items():
      Ctx()._symbolings_logger.log_branch_revision(
          cvs_branch, svn_commit.revnum)

  def process_changeset(self, changeset, timestamp):
    """Process CHANGESET, using TIMESTAMP for all of its entries.

    The changesets must be fed to this function in proper dependency
    order."""

    if isinstance(changeset, OrderedChangeset):
      self._process_revision_changeset(changeset, timestamp)
    elif isinstance(changeset, TagChangeset):
      self._process_tag_changeset(changeset, timestamp)
    elif isinstance(changeset, BranchChangeset):
      self._process_branch_changeset(changeset, timestamp)
    else:
      raise TypeError('Illegal changeset %r' % changeset)


