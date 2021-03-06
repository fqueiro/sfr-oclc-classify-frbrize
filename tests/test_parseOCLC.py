from lxml import etree
import unittest
from unittest.mock import MagicMock, patch

from lib.parsers.parseOCLC import readFromClassify, loadEditions, extractAndAppendEditions
from lib.dataModel import WorkRecord
from lib.outputManager import OutputManager


class TestOCLCParse(unittest.TestCase):
    @patch.object(OutputManager, 'checkRecentQueries', return_value=False)
    def test_classify_read(self, mockCheck):
        mockXML = MagicMock()
        work = etree.Element(
            'work',
            title='Test Work',
            editions='1',
            holdings='1',
            eholdings='1',
            owi='1111111',
        )
        start = etree.Element('start')
        start.text = '0'
        work.text = '0000000000'
        mockXML.find.side_effect = [work, start]
        mockXML.findall.return_value = []
        resWork, resCount, oclcID = readFromClassify(mockXML, 'testUUID')
        self.assertIsInstance(resWork, WorkRecord)
        self.assertEqual(resCount, 1)
        self.assertEqual(oclcID, '0000000000')
        mockCheck.assert_called_once_with('lookup/owi/1111111/0')

    @patch('lib.parsers.parseOCLC.parseEdition', return_value=True)
    def test_loadEditions(self, mockParse):
        testEditions = [i for i in range(16)]
        outEds = loadEditions(testEditions)
        self.assertEqual(len(outEds), 16)
    
    @patch('lib.parsers.parseOCLC.loadEditions')
    def test_extractEditions(self, mockLoad):
        mockXML = MagicMock()
        mockXML.findall.return_value = ['ed1', 'ed2', 'ed3']
        mockWork = MagicMock()
        mockWork.instances = []
        mockLoad.return_value = [1, 2, 3]
        extractAndAppendEditions(mockWork, mockXML)
        self.assertEqual(mockWork.instances, [1, 2, 3])
        mockLoad.assert_called_once_with(['ed1', 'ed2', 'ed3'])
