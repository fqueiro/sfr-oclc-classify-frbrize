import subprocess
import sys
import os
import shutil
import re
import yaml
import json

import boto3
import botocore

from helpers.logHelpers import createLog
from helpers.errorHelpers import InvalidExecutionType
from helpers.configHelpers import setEnvVars
from helpers.clientHelpers import createEventMapping

logger = createLog('runScripts')

# This script is invoked by the Makefile in root to execute various
# commands around a python lambda. This includes deployment, local invocations,
# and tests/test coverage. It attempts to replicate some of the functionality
# provided through node/package.json
# H/T to Paul Beaudoin for the inspiration


def main():

    if len(sys.argv) != 2:
        logger.warning('This script takes one, and only one, argument!')
        sys.exit(1)
    runType = sys.argv[1]

    if re.match(r'^(?:development|qa|production)', runType):
        logger.info('Deploying lambda to {} environment'.format(runType))
        setEnvVars(runType)
        subprocess.run([
            'lambda',
            'deploy',
            '--config-file',
            'run_config.yaml',
            '--requirements',
            'requirements.txt'
        ])
        createEventMapping(runType)
        os.remove('run_config.yaml')

    elif re.match(r'^run-local', runType):
        logger.info('Running test locally with development environment')
        env = 'development'
        setEnvVars(env)
        subprocess.run([
            'lambda',
            'invoke',
            '-v',
            '--config-file',
            'run_config.yaml'
        ])
        os.remove('run_config.yaml')

    elif re.match(r'^build-(?:development|qa|production)', runType):
        env = runType.replace('build-', '')
        logger.info('Building package for {} environment, will be in dist/'.format(env))  # noqa: E501
        setEnvVars(env)
        subprocess.run([
            'lambda',
            'build',
            '--requirements',
            'requirements.txt',
            '--config-file',
            'run_config.yaml'
        ])
        os.remove('run_config.yaml')

    else:
        logger.error('Execution type not recognized! {}'.format(runType))
        raise InvalidExecutionType('{} is not a valid command'.format(runType))


if __name__ == '__main__':
    main()
