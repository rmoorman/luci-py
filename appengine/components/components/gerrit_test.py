#!/usr/bin/env python
# Copyright 2014 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

import httplib
import json
import sys
import unittest

from test_support import test_env
test_env.setup_test_env()

import mock
from google.appengine.api import urlfetch

from components import auth
from components import gerrit
from test_support import test_case


HOSTNAME = 'chromium-review.googlesource.com'
SHORT_CHANGE_ID = 'I7c1811882cf59c1dc55018926edb6d35295c53b8'
CHANGE_ID = 'project~master~%s' % SHORT_CHANGE_ID
REVISION = '404d1697dca23824bc1130061a5bd2be4e073922'


class GerritFetchTestCase(test_case.TestCase):
  def setUp(self):
    super(GerritFetchTestCase, self).setUp()
    self.response = mock.Mock(
        status_code=httplib.OK,
        headers={},
        content='',
    )
    self.mock(urlfetch, 'fetch', mock.Mock(return_value=self.response))
    self.mock(auth, 'get_access_token', mock.Mock(return_value=('token', 0.0)))

  def test_fetch(self):
    req_body = {'b': 2}
    self.response.content = ')]}\'{"a":1}'
    actual = gerrit.fetch_json(
        'localhost', 'p', body=req_body, query_params={'p': 1})
    self.assertEqual(actual, {'a': 1})
    fetch_args, fetch_kwargs = urlfetch.fetch.call_args
    self.assertEqual(fetch_args[0], 'https://localhost/a/p?p=1')
    self.assertEqual(json.loads(fetch_kwargs.get('payload')), req_body)

  def test_not_found(self):
    self.response.status_code = httplib.NOT_FOUND
    result = gerrit.fetch_json('localhost', 'p')
    self.assertIsNone(result)

  def test_auth_failure(self):
    self.response.status_code = httplib.FORBIDDEN
    with self.assertRaises(auth.AuthorizationError):
      gerrit.fetch_json('localhost', 'a')

  def test_bad_prefix(self):
    self.response.content = 'abc'
    with self.assertRaises(gerrit.Error):
      gerrit.fetch_json('localhost', 'a')


class GerritTestCase(test_case.TestCase):
  def setUp(self):
    super(GerritTestCase, self).setUp()
    self.mock(gerrit, 'fetch_json', mock.Mock())

  def test_get_change(self):
    req_path = 'changes/%s?o=ALL_REVISIONS' % CHANGE_ID
    change_reponse = {
      'id': CHANGE_ID,
      'project': 'project',
      'branch': 'master',
      'hashtags': [],
      'change_id': SHORT_CHANGE_ID,
      'subject': 'My change',
      'status': 'NEW',
      'created': '2014-10-17 18:24:39.193000000',
      'updated': '2014-10-17 20:44:48.338000000',
      'mergeable': True,
      'insertions': 10,
      'deletions': 11,
      '_sortkey': '0030833c0002bff9',
      '_number': 180217,
      'owner': {
        'name': 'John Doe',
      },
      'current_revision': REVISION,
      'revisions': {
        REVISION: {
          '_number': 1,
          'fetch': {
            'http': {
              'url': 'https://chromium.googlesource.com/html-office',
              'ref': 'refs/changes/80/123/1',
            }
          },
        },
      },
    }

    gerrit.fetch_json.return_value = change_reponse

    change = gerrit.get_change(HOSTNAME, CHANGE_ID)

    gerrit.fetch_json.assert_called_with(HOSTNAME, req_path)
    self.assertIsNotNone(change)
    self.assertEqual(change.change_id, SHORT_CHANGE_ID)
    self.assertEqual(change.branch, 'master')
    self.assertEqual(change.project, 'project')
    self.assertEqual(change.owner.name, 'John Doe')
    self.assertEqual(change.current_revision, REVISION)

    # smoke test for branch coverage
    change = gerrit.get_change(
        HOSTNAME, CHANGE_ID, include_all_revisions=False,
        include_owner_details=True)

  def test_set_review(self):
    req_path = 'changes/%s/revisions/%s/review' % (CHANGE_ID, REVISION)
    labels = {'Verified': 1 }
    gerrit.fetch_json.return_value = {'labels': labels}

    gerrit.set_review(
        HOSTNAME, CHANGE_ID, REVISION, message='Hi!', labels=labels)

    expected_body = {
        'message': 'Hi!',
        'labels': labels,
    }
    gerrit.fetch_json.assert_called_with(
        HOSTNAME, req_path, method='POST', body=expected_body)

    # Test with "notify" parameter.
    gerrit.set_review(
        HOSTNAME, CHANGE_ID, REVISION, message='Hi!', labels=labels,
        notify='all')
    gerrit.fetch_json.assert_called_with(
        HOSTNAME,
        req_path,
        method='POST',
        body={
          'message': 'Hi!',
          'labels': labels,
          'notify': 'ALL',
        })

    with self.assertRaises(AssertionError):
      gerrit.set_review(HOSTNAME, CHANGE_ID, REVISION, notify='Argh!')


if __name__ == '__main__':
  if '-v' in sys.argv:
    unittest.TestCase.maxDiff = None
  unittest.main()
