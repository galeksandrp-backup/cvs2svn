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

"""Functions to sort large files.

The functions in this module were originally downloaded from the
following URL:

    http://code.activestate.com/recipes/466302/

It was apparently submitted by Nicolas Lehuen on Tue, 17 Jan 2006.
According to the terms of service of that website, the code is usable
under the MIT license.

"""


import os
import heapq
import itertools
import tempfile


def merge(chunks, key=None):
  if key is None:
    key = lambda x : x

  values = []

  for index, chunk in enumerate(chunks):
    try:
      iterator = iter(chunk)
      value = iterator.next()
    except StopIteration:
      try:
        chunk.close()
        os.remove(chunk.name)
        chunks.remove(chunk)
      except:
        pass
    else:
      heapq.heappush(values, ((key(value), index, value, iterator, chunk)))

  while values:
    k, index, value, iterator, chunk = heapq.heappop(values)
    yield value
    try:
      value = iterator.next()
    except StopIteration:
      try:
        chunk.close()
        os.remove(chunk.name)
        chunks.remove(chunk)
      except:
        pass
    else:
      heapq.heappush(values, (key(value), index, value, iterator, chunk))


def sort_file(input, output, key=None, buffer_size=32000, tempdirs=[]):
  if not tempdirs:
    tempdirs = [tempfile.gettempdir()]

  input_file = file(input, 'rb', 64*1024)
  try:
    input_iterator = iter(input_file)

    chunks = []
    try:
      for tempdir in itertools.cycle(tempdirs):
        current_chunk = list(itertools.islice(input_iterator, buffer_size))
        if not current_chunk:
          break
        current_chunk.sort(key=key)
        (fd, filename) = tempfile.mkstemp(
            '', 'sort%06i' % (len(chunks),), tempdir, False
            )
        os.close(fd)
        output_chunk = open(filename, 'w+b', 64*1024)
        output_chunk.writelines(current_chunk)
        output_chunk.flush()
        output_chunk.seek(0)
        chunks.append(output_chunk)
    except:
      for chunk in chunks:
        try:
          chunk.close()
          os.remove(chunk.name)
        except:
          pass
      if output_chunk not in chunks:
        try:
          output_chunk.close()
          os.remove(output_chunk.name)
        except:
          pass
      return
  finally:
    input_file.close()

  output_file = file(output, 'wb', 64*1024)
  try:
    output_file.writelines(merge(chunks, key))
  finally:
    for chunk in chunks:
      try:
        chunk.close()
        os.remove(chunk.name)
      except:
        pass
    output_file.close()


