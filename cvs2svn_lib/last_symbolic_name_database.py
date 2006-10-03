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

"""This module contains database facilities used by cvs2svn."""


from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.common import OP_DELETE
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import Database


class LastSymbolicNameDatabase:
  """Passing every CVSRevision in s-revs to this class will result in
  a Database whose key is the last CVS Revision a symbolicname was
  seen in, and whose value is a list of all symbolicnames that were
  last seen in that revision."""

  def __init__(self):
    # A map { symbol_id : cvs_rev } of the chronologically last
    # CVSRevision that had the symbol as a tag or branch.  Once we've
    # gone through all the revs, symbols.keys() will be a list of all
    # tag and branch symbol_ids, and their corresponding values will
    # be the last CVS revision that the symbol was used in.
    self._symbols = {}

  def log_revision(self, cvs_rev):
    """Gather last CVS Revision for symbolic name info and tag info."""

    for tag_id in cvs_rev.tag_ids:
      cvs_tag = Ctx()._cvs_items_db[tag_id]
      old_cvs_rev = self._symbols.get(cvs_tag.symbol.id)
      if old_cvs_rev is None or old_cvs_rev.timestamp < cvs_rev.timestamp:
        self._symbols[cvs_tag.symbol.id] = cvs_rev
    if cvs_rev.op != OP_DELETE:
      for branch_id in cvs_rev.branch_ids:
        cvs_branch = Ctx()._cvs_items_db[branch_id]
        old_cvs_rev = self._symbols.get(cvs_branch.symbol.id)
        if old_cvs_rev is None or old_cvs_rev.timestamp < cvs_rev.timestamp:
          self._symbols[cvs_branch.symbol.id] = cvs_rev

  def create_database(self):
    """Create the SYMBOL_LAST_CVS_REVS_DB.

    The database will hold an inversion of symbols above--a map {
    cvs_rev.id : [ symbol, ... ] of symbols that close in each
    CVSRevision."""

    symbol_revs_db = Database(
        artifact_manager.get_temp_file(config.SYMBOL_LAST_CVS_REVS_DB),
        DB_OPEN_NEW)
    for symbol_id, cvs_rev in self._symbols.items():
      rev_key = '%x' % (cvs_rev.id,)
      ary = symbol_revs_db.get(rev_key, [])
      ary.append(symbol_id)
      symbol_revs_db[rev_key] = ary


