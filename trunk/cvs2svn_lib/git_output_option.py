# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2007 CollabNet.  All rights reserved.
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

"""Classes for outputting the converted repository to git.

For information about the format allowed by git-fast-import, see:

    http://www.kernel.org/pub/software/scm/git/docs/git-fast-import.html

"""


from __future__ import generators

import bisect

from cvs2svn_lib.boolean import *
from cvs2svn_lib.set_support import *
from cvs2svn_lib import config
from cvs2svn_lib.common import InternalError
from cvs2svn_lib.common import FatalError
from cvs2svn_lib.common import warning_prefix
from cvs2svn_lib.log import Log
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.openings_closings import SymbolingsReader
from cvs2svn_lib.symbol import Trunk
from cvs2svn_lib.cvs_item import CVSRevisionModification
from cvs2svn_lib.cvs_item import CVSRevisionDelete
from cvs2svn_lib.cvs_item import CVSRevisionNoop
from cvs2svn_lib.output_option import OutputOption
from cvs2svn_lib.svn_revision_range import RevisionScores


# The branch name to use for the "tag fixup branches".  The
# git-fast-import documentation suggests using 'TAG_FIXUP' (outside of
# the refs/heads namespace), but this is currently broken.  Use a name
# containing '.', which is not allowed in CVS symbols, to avoid
# conflicts (though of course a conflict could still result if the
# user requests symbol transformations).
FIXUP_BRANCH_NAME = 'refs/heads/TAG.FIXUP'


class GitOutputOption(OutputOption):
  """An OutputOption that outputs to a git-fast-import formatted file."""

  # The offset added to svn revision numbers to create a number to use
  # as a git-fast-import commit mark.  This value needs to be large to
  # avoid conflicts with blob marks.
  _mark_offset = 1000000000

  def __init__(self, dump_filename):
    # The file to which to write the git-fast-import commands:
    self.dump_filename = dump_filename

  def register_artifacts(self, which_pass):
    # These artifacts are needed for SymbolingsReader:
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OPENINGS_CLOSINGS_SORTED, which_pass
        )
    artifact_manager.register_temp_file_needed(
        config.SYMBOL_OFFSETS_DB, which_pass
        )

  def check(self):
    Log().warn('!!!!! WARNING: Git output is highly experimental !!!!!')
    if Ctx().cross_project_commits:
      raise FatalError(
          'Git output is not supported with cross-project commits'
          )
    if Ctx().cross_branch_commits:
      raise FatalError(
          'Git output is not supported with cross-branch commits'
          )
    if Ctx().username is None:
      raise FatalError(
          'Git output requires a default commit username'
          )

  def check_symbols(self, symbol_map):
    # FIXME: What constraints does git impose on symbols?
    pass

  def setup(self, svn_rev_count):
    self._symbolings_reader = SymbolingsReader()
    self.f = open(self.dump_filename, 'wb')

    # The youngest revnum that has been committed so far:
    self._youngest = 0

    # A map {lod : [(revnum, mark)]} giving each of the revision
    # numbers in which there was a commit to lod, and the
    # corresponding mark.
    self._marks = {}

  def _create_commit_mark(self, lod, revnum):
    assert revnum >= self._youngest
    mark = GitOutputOption._mark_offset + revnum
    self._marks.setdefault(lod, []).append((revnum, mark))
    self._youngest = revnum
    return mark

  def _get_author(svn_commit):
    """Return the author to be used for SVN_COMMIT.

    Return the author in the form needed by git; that is, 'foo <bar>'."""

    author = svn_commit.get_author()
    try:
      author = Ctx().cvs_author_decoder(author).encode('utf8')
    except UnicodeError:
      Log().warn('%s: problem encoding author:' % warning_prefix)
      Log().warn("  author: '%s'" % (author,))

    return '%s <%s>' % (author, author,)

  _get_author = staticmethod(_get_author)

  def _get_log_msg(svn_commit):
    log_msg = svn_commit.get_log_msg()
    try:
      log_msg = Ctx().cvs_log_decoder(log_msg).encode('utf8')
    except UnicodeError:
      Log().warn('%s: problem encoding log message:' % warning_prefix)
      Log().warn("  log:    '%s'" % log_msg.rstrip())

    return log_msg

  _get_log_msg = staticmethod(_get_log_msg)

  def process_initial_project_commit(self, svn_commit):
    # Nothing to do.
    pass

  def process_primary_commit(self, svn_commit):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    lods = set()
    for cvs_rev in svn_commit.get_cvs_items():
      lods.add(cvs_rev.lod)
    if len(lods) != 1:
      raise InternalError('Commit affects %d LODs' % (len(lods),))
    lod = lods.pop()
    if isinstance(lod, Trunk):
      # FIXME: is this correct?:
      self.f.write('commit refs/heads/master\n')
    else:
      self.f.write('commit refs/heads/%s\n' % (lod.name,))
    self.f.write(
        'mark :%d\n'
        % (self._create_commit_mark(lod, svn_commit.revnum),)
        )
    self.f.write(
        'committer %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))
    for cvs_rev in svn_commit.get_cvs_items():
      if isinstance(cvs_rev, CVSRevisionNoop):
        pass

      elif isinstance(cvs_rev, CVSRevisionDelete):
        self.f.write('D %s\n' % (cvs_rev.cvs_file.cvs_path,))

      elif isinstance(cvs_rev, CVSRevisionModification):
        if cvs_rev.cvs_file.executable:
          mode = '100755'
        else:
          mode = '100644'

        self.f.write(
            'M %s :%d %s\n'
            % (mode, cvs_rev.revision_recorder_token,
               cvs_rev.cvs_file.cvs_path,)
            )

    self.f.write('\n')

  def process_post_commit(self, svn_commit):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    source_lods = set()
    for cvs_rev in svn_commit.cvs_revs:
      source_lods.add(cvs_rev.lod)
    if len(source_lods) != 1:
      raise InternalError('Commit is from %d LODs' % (len(source_lods),))
    source_lod = source_lods.pop()
    # FIXME: is this correct?:
    self.f.write('commit refs/heads/master\n')
    self.f.write(
        'mark :%d\n'
        % (self._create_commit_mark(None, svn_commit.revnum),)
        )
    self.f.write(
        'committer %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))
    self.f.write(
        'merge :%d\n'
        % (self._get_source_mark(source_lod, svn_commit.revnum),)
        )
    for cvs_rev in svn_commit.cvs_revs:
      if isinstance(cvs_rev, CVSRevisionNoop):
        pass

      elif isinstance(cvs_rev, CVSRevisionDelete):
        self.f.write('D %s\n' % (cvs_rev.cvs_file.cvs_path,))

      elif isinstance(cvs_rev, CVSRevisionModification):
        if cvs_rev.cvs_file.executable:
          mode = '100755'
        else:
          mode = '100644'

        self.f.write(
            'M %s :%d %s\n'
            % (mode, cvs_rev.revision_recorder_token,
               cvs_rev.cvs_file.cvs_path,)
            )

      else:
        raise InternalError('Unexpected CVSRevision type: %s' % (cvs_rev,))

    self.f.write('\n')

  def _get_source_groups(self, svn_commit):
    """Return groups of sources for SVN_COMMIT.

    SVN_COMMIT is an instance of SVNSymbolCommit.  Yield tuples
    (source_lod, svn_revnum, cvs_symbols) where source_lod is the line
    of development and svn_revnum is the revision that should serve as
    a source, and cvs_symbols is a list of CVSSymbolItems that can be
    copied from that source.  The groups are returned in arbitrary
    order."""

    # Get a map {CVSSymbol : SVNRevisionRange}:
    range_map = self._symbolings_reader.get_range_map(svn_commit)

    # range_map, split up into one map per LOD; i.e., {LOD :
    # {CVSSymbol : SVNRevisionRange}}:
    lod_range_maps = {}

    for (cvs_symbol, range) in range_map.iteritems():
      lod_range_map = lod_range_maps.get(range.source_lod)
      if lod_range_map is None:
        lod_range_map = {}
        lod_range_maps[range.source_lod] = lod_range_map
      lod_range_map[cvs_symbol] = range

    for (lod, lod_range_map) in lod_range_maps.iteritems():
      while lod_range_map:
        revision_scores = RevisionScores(lod_range_map.values())
        (source_lod, revnum, score) = revision_scores.get_best_revnum()
        assert source_lod == lod
        cvs_symbols = []
        for (cvs_symbol, range) in lod_range_map.items():
          if revnum in range:
            cvs_symbols.append(cvs_symbol)
            del lod_range_map[cvs_symbol]
        yield (lod, revnum, cvs_symbols)

  def _get_source_mark(self, source_lod, revnum):
    """Return the mark active at REVNUM on SOURCE_LOD."""

    modifications = self._marks[source_lod]
    i = bisect.bisect_left(modifications, (revnum + 1,)) - 1
    (revnum, mark) = modifications[i]
    return mark

  def _process_symbol_commit(self, svn_commit, git_branch, mark):
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    self.f.write('commit %s\n' % (git_branch,))
    self.f.write('mark :%d\n' % (mark,))
    self.f.write(
        'committer %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))

    source_groups = list(self._get_source_groups(svn_commit))
    for (source_lod, source_revnum, cvs_symbols,) in source_groups:
      self.f.write(
          'merge :%d\n'
          % (self._get_source_mark(source_lod, source_revnum),)
          )

    for (source_lod, source_revnum, cvs_symbols,) in source_groups:
      for cvs_symbol in cvs_symbols:
        if cvs_symbol.cvs_file.executable:
          mode = '100755'
        else:
          mode = '100644'

        self.f.write(
            'M %s :%d %s\n'
            % (mode, cvs_symbol.revision_recorder_token,
               cvs_symbol.cvs_file.cvs_path,)
            )

    self.f.write('\n')

  def process_branch_commit(self, svn_commit):
    self._process_symbol_commit(
        svn_commit, 'refs/heads/%s' % (svn_commit.symbol.name,),
        self._create_commit_mark(svn_commit.symbol, svn_commit.revnum),
        )

  def process_tag_commit(self, svn_commit):
    # FIXME: For now we create a fixup branch with the same name as
    # the tag, then the tag.  We never delete the fixup branch.  Also,
    # a fixup branch is created even if the tag could be created from
    # a single source.
    author = self._get_author(svn_commit)
    log_msg = self._get_log_msg(svn_commit)

    mark = self._create_commit_mark(svn_commit.symbol, svn_commit.revnum)
    self._process_symbol_commit(svn_commit, FIXUP_BRANCH_NAME, mark)
    self.f.write('tag %s\n' % (svn_commit.symbol.name,))
    self.f.write('from :%d\n' % (mark,))
    self.f.write(
        'tagger %s %d +0000\n' % (author, svn_commit.date,)
        )
    self.f.write('data %d\n' % (len(log_msg),))
    self.f.write('%s\n' % (log_msg,))

    self.f.write('reset %s\n' % (FIXUP_BRANCH_NAME,))
    self.f.write('\n')

  def cleanup(self):
    self.f.close()
    del self.f
    self._symbolings_reader.close()
    del self._symbolings_reader


