# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
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

"""Store the context (options, etc) for a cvs2svn run."""


import os
import textwrap

from cvs2svn_lib import config
from cvs2svn_lib.common import CVSTextDecoder


class Ctx:
  """Session state for this run of cvs2svn.  For example, run-time
  options are stored here.  This class is a Borg (see
  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66531)."""

  __shared_state = { }

  def __init__(self):
    self.__dict__ = self.__shared_state
    if self.__dict__:
      return
    # Else, initialize to defaults.
    self.set_defaults()

  def set_defaults(self):
    """Set all parameters to their default values."""

    self.output_option = None
    self.dry_run = False
    self.revision_excluder = None
    self.revision_reader = None
    self.svnadmin_executable = config.SVNADMIN_EXECUTABLE
    self.trunk_only = False
    self.include_empty_directories = False
    self.prune = True
    self.cvs_author_decoder = CVSTextDecoder(['ascii'])
    self.cvs_log_decoder = CVSTextDecoder(['ascii'])
    self.cvs_filename_decoder = CVSTextDecoder(['ascii'])
    self.decode_apple_single = False
    self.symbol_info_filename = None
    self.username = None
    self.svn_property_setters = []
    self.tmpdir = 'cvs2svn-tmp'
    self.skip_cleanup = False
    self.keep_cvsignore = False
    self.cross_project_commits = True
    self.cross_branch_commits = True
    self.retain_conflicting_attic_files = False

    # textwrap.TextWrapper instance to be used for wrapping log messages:
    self.text_wrapper = textwrap.TextWrapper(width=76)

    self.initial_project_commit_message = (
        'Standard project directories initialized by cvs2svn.'
        )
    self.post_commit_message = (
        'This commit was generated by cvs2svn to compensate for '
        'changes in r%(revnum)d, which included commits to RCS files '
        'with non-trunk default branches.'
        )
    self.symbol_commit_message = (
        "This commit was manufactured by cvs2svn to create %(symbol_type)s "
        "'%(symbol_name)s'."
        )
    self.tie_tag_ancestry_message = (
        "This commit was manufactured by cvs2svn to tie ancestry for "
        "tag '%(symbol_name)s' back to the source branch."
        )


  def get_temp_filename(self, basename):
    return os.path.join(self.tmpdir, basename)

  def clean(self):
    """Dispose of items in our dictionary that are not intended to
    live past the end of a pass (identified by exactly one leading
    underscore)."""

    for attr in self.__dict__.keys():
      if (attr.startswith('_') and not attr.startswith('__')
          and not attr.startswith('_Ctx__')):
        delattr(self, attr)


