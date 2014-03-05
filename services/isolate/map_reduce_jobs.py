# Copyright 2013 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

import logging
import os
import sys

# Map-reduce library expects 'mapreduce' package to be in sys.path.
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.join(ROOT_DIR, 'third_party'))

from mapreduce import control
from mapreduce import main

import config
import gcs


# Task queue name to run all map reduce jobs on.
MAP_REDUCE_TASK_QUEUE = 'map-reduce-jobs'


# All registered mapreduce jobs, will be displayed on admin page.
# All parameters are passed as is to mapreduce.control.start_map.
MAP_REDUCE_JOBS = {
  'find_missing_gs_files': {
    'name': 'Report missing GS files',
    'handler_spec': 'map_reduce_jobs.detect_missing_gs_file_mapper',
    'reader_spec': 'mapreduce.input_readers.DatastoreInputReader',
    'mapper_parameters': {
      'entity_kind': 'handlers.ContentEntry',
      'batch_size': 20,
    },
    'shard_count': 64,
    'queue_name': MAP_REDUCE_TASK_QUEUE,
  },
  'delete_broken_entries': {
    'name': 'Delete entries that do not have corresponding GS files',
    'handler_spec': 'map_reduce_jobs.delete_broken_entries_mapper',
    'reader_spec': 'mapreduce.input_readers.DatastoreInputReader',
    'mapper_parameters': {
      'entity_kind': 'handlers.ContentEntry',
      'batch_size': 20,
    },
    'shard_count': 64,
    'queue_name': MAP_REDUCE_TASK_QUEUE,
  },
}


def launch_job(job_id):
  """Launches a job given its key from MAP_REDUCE_JOBS dict."""
  assert job_id in MAP_REDUCE_JOBS, 'Unknown mapreduce job id %s' % job_id
  job_def = MAP_REDUCE_JOBS[job_id]
  return control.start_map(base_path='/internal/mapreduce', **job_def)


def is_good_content_entry(entry):
  """True if ContentEntry is not broken.

  ContentEntry is broken if it is in old format (before content namespace
  were sharded) or corresponding Google Storage file doesn't exist.
  """
  # New entries use GS file path as ids. File path is always <namespace>/<hash>.
  entry_id = entry.key.id()
  if '/' not in entry_id:
    return False
  # Content is inline, entity doesn't have GS file attached -> it is fine.
  if entry.content is not None:
    return True
  # Ensure GS file exists.
  return bool(gcs.get_file_info(config.settings().gs_bucket, entry_id))


### Actual mappers


def detect_missing_gs_file_mapper(entry):
  """Mapper that takes ContentEntry and logs to output if GS file is missing."""
  if not is_good_content_entry(entry):
    logging.error('MR: found bad entry\n%s', entry.key.id())


def delete_broken_entries_mapper(entry):
  """Mapper that deletes ContentEntry entities that are broken."""
  if not is_good_content_entry(entry):
    # MR framework disables memcache on a context level. Explicitly request
    # to cleanup memcache, otherwise the rest of the isolate service will still
    # think that entity exists.
    entry.key.delete(use_memcache=True)
    logging.error('MR: deleted bad entry\n%s', entry.key.id())


# Export mapreduce WSGI application as 'app'.
# Used in app.yaml and module-backend.yaml for mapreduce/* routes.
app = main.APP
