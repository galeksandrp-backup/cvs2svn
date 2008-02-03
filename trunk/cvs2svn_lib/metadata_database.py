# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2007 CollabNet.  All rights reserved.
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

"""This module contains classes to manage CVSRevision metadata."""


import sha

from cvs2svn_lib.boolean import *
from cvs2svn_lib import config
from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.context import Ctx
from cvs2svn_lib.log import Log
from cvs2svn_lib.artifact_manager import artifact_manager
from cvs2svn_lib.database import IndexedDatabase
from cvs2svn_lib.key_generator import KeyGenerator
from cvs2svn_lib.serializer import MarshalSerializer


def MetadataDatabase(mode):
  """A Database to store metadata about CVSRevisions.

  This database manages a map

      id -> (author, log_msg,)

  where id is a unique identifier for a set of metadata."""

  return IndexedDatabase(
      artifact_manager.get_temp_file(config.METADATA_STORE),
      artifact_manager.get_temp_file(config.METADATA_INDEX_TABLE),
      mode, MarshalSerializer(),
      )


class MetadataLogger:
  """Store and generate IDs for the metadata associated with CVSRevisions.

  We want CVSRevisions that might be able to be combined to have the
  same metadata ID, so we want a one-to-one relationship id <->
  metadata.  We could simply construct a map {metadata : id}, but the
  map would grow too large.  Therefore, we generate a digest
  containing the significant parts of the metadata, and construct a
  map {digest : id}.

  To get the ID for a new set of metadata, we first create the digest.
  If there is already an ID registered for that digest, we simply
  return it.  If not, we generate a new ID, store the metadata in the
  metadata database under that ID, record the mapping {digest : id},
  and return the new id.

  What metadata is included in the digest?  The author, log_msg,
  project_id (if Ctx().cross_project_commits is not set), and
  branch_name (if Ctx().cross_branch_commits is not set)."""

  def __init__(self, metadata_db):
    self._metadata_db = metadata_db

    # A map { digest : id }:
    self._digest_to_id = {}

    # A key_generator to generate keys for metadata that haven't been
    # seen yet:
    self.key_generator = KeyGenerator()

  def store(self, project, branch_name, author, log_msg):
    """Store the metadata and return its id.

    Locate the record for a commit with the specified (PROJECT,
    BRANCH_NAME, AUTHOR, LOG_MSG) and return its id.  (Depending on
    policy, not all of these items are necessarily used when creating
    the unique id.)  If there is no such record, create one and return
    its newly-generated id."""

    key = [author, log_msg]
    if not Ctx().cross_project_commits:
      key.append('%x' % project.id)
    if not Ctx().cross_branch_commits:
      key.append(branch_name or '')

    digest = sha.new('\0'.join(key)).digest()
    try:
      # See if it is already known:
      return self._digest_to_id[digest]
    except KeyError:
      id = self.key_generator.gen_id()
      self._digest_to_id[digest] = id
      self._metadata_db[id] = (author, log_msg,)
      return id


