import unittest
from unittest.mock import patch, mock_open, call
from botocore.stub import Stubber
import botocore
import json
import os
os.environ['OUTPUT_REGION'] = 'us-test-1'

from lib.kinesisWrite import KinesisOutput
from helpers.errorHelpers import KinesisError

class TestKinesis(unittest.TestCase):

    @patch.dict('os.environ', {'OUTPUT_KINESIS': 'tester', 'OUTPUT_SHARD': '0'})
    def test_putRecord(self):
        kinesis = KinesisOutput()
        stubber = Stubber(kinesis.KINESIS_CLIENT)
        expResp = {
            'ShardId': '1',
            'SequenceNumber': '0'
        }

        record = {'test': 'data'}

        body = json.dumps({
            'status': 200,
            'stage': 'oclc-lookup',
            'data': record
        })

        expected_params = {
            'Data': body,
            'StreamName': 'tester',
            'PartitionKey': '0'
        }

        stubber.add_response('put_record', expResp, expected_params)
        stubber.activate()

        kinesis.putRecord(record)

    @patch.dict('os.environ', {'OUTPUT_KINESIS': 'tester', 'OUTPUT_SHARD': '0'})
    def test_putRecord_err(self):
        kinesis = KinesisOutput()
        stubber = Stubber(kinesis.KINESIS_CLIENT)

        record = {'test': 'data'}

        body = json.dumps({
            'status': 200,
            'stage': 'oclc-lookup',
            'data': record
        })

        expected_params = {
            'Data': body,
            'StreamName': 'tester',
            'PartitionKey': '0'
        }

        stubber.add_client_error('put_record', expected_params=expected_params)
        stubber.activate()
        try:
            kinesis.putRecord(record)
        except KinesisError:
            pass
        self.assertRaises(KinesisError)