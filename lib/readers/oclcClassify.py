import requests
import os
from lxml import etree

from helpers.errorHelpers import OCLCError, DataError
from helpers.logHelpers import createLog

from lib.outputManager import OutputManager

logger = createLog('classify_read')

NAMESPACE = {
    None: 'http://classify.oclc.org'
}


def classifyRecord(searchType, searchFields, workUUID, start=0):
    """Generates a query for the OCLC Classify service and returns the raw
    XML response received from that service. This method takes 3 arguments:
    - searchType: identifier|authorTitle
    - searchFields: identifier+idType|authors+title
    - uuid: UUID of the parent work record"""
    try:
        classifyQuery = QueryManager(
            searchType,
            searchFields.get('identifier', None),
            searchFields.get('idType', None),
            searchFields.get('authors', None),
            searchFields.get('title', None),
            start
        )
        classifyQuery.generateQueryURL()
        logger.info('Fetching data for url: {}'.format(classifyQuery.query))
    except DataError as err:
        logger.warning('Unable to create valid Classify query')
        logger.debug(err)
        raise OCLCError('Invalid query options provided, unable to execute.')

    # Load Query Response from OCLC Classify
    logger.debug('Making Classify request')
    rawData = classifyQuery.execQuery()

    # Parse response, and if it is a Multi-Work response, parse further
    logger.debug('Parsing Classify Response')

    return parseClassify(rawData, workUUID, classifyQuery.title, classifyQuery.author)


def parseClassify(rawXML, workUUID, checkTitle, checkAuthor):
    """Parses results received from Classify. Response is based of the code
    recieved from the service, generically it will response with the XML of a
    work record or None if it recieves a different response code.

    If a multi-response is recieved, those identifiers are put back into the
    processing stream, this will recurse until a single work record is
    found."""
    try:
        parseXML = etree.fromstring(rawXML.encode('utf-8'))
    except etree.XMLSyntaxError as err:
        logger.error('Classify returned invalid XML')
        logger.debug(err)
        raise OCLCError('Received invalid XML from OCLC service')

    # Check for the type of response we recieved
    # 2: Single-Work Response
    # 4: Multi-Work Response
    # 102: No Results found for query
    # Other: Raise Error
    responseXML = parseXML.find('.//response', namespaces=NAMESPACE)
    responseCode = int(responseXML.get('code'))

    if responseCode == 102:
        logger.info('Did not find any information for this query')
        raise OCLCError('No work records found in OCLC Classify Service')
    elif responseCode == 2:
        logger.debug('Got Single Work, parsing work and edition data')
        return parseXML
    elif responseCode == 4:
        logger.debug('Got Multiwork response, iterate through works to get details')
        works = parseXML.findall('.//work', namespaces=NAMESPACE)
        for work in works:
            oclcID = work.get('wi')
            oclcTitle = work.get('title', None)
            oclcAuthors = work.get('author', None)
            if checkTitle is not None:
                if authorTitleCheck(
                    checkTitle.lower(),
                    checkAuthor.lower(),
                    oclcTitle.lower(),
                    oclcAuthors.lower()
                ) is False:
                    logger.info('Found author/title mismatch between {} and {}. Skipping'.format(
                        checkTitle,
                        oclcTitle
                    ))
                    continue
            if OutputManager.checkRecentQueries('classify/oclc/{}'.format(oclcID)) is False:
                OutputManager.putQueue({
                    'type': 'identifier',
                    'uuid': workUUID,
                    'fields': {
                        'idType': 'oclc',
                        'identifier': oclcID
                    }
                }, os.environ['CLASSIFY_QUEUE'])

        raise OCLCError('Received Multi-Work response from Classify, returned records to input stream')
    else:
        raise OCLCError('Recieved unexpected response {} from Classify'.format(responseCode))

def getJaccardScore(title, mainTitle):
    tGrams = ngrams(title, n=3)
    mGrams = ngrams(mainTitle, n=3)
    return float(len(tGrams & mGrams)) / len(tGrams | mGrams)

def ngrams(string, n=3):
    ngrams = zip(*[string[i:] for i in range(n)])
    return set([''.join(ngram) for ngram in ngrams])

def authorTitleCheck(startTitle, startAuthor, oclcTitle, oclcAuthor):
    jaccScore = getJaccardScore(oclcTitle, startTitle)
    innerAuthor, outerAuthor = sortStrings(startAuthor, oclcAuthor)
    if jaccScore >= 0.75 and innerAuthor in outerAuthor:
        logger.debug('Found match for {} with score {}'.format(
            oclcTitle, jaccScore
        ))
        return True

    return False

def sortStrings(str1, str2):
    if len(str1) < len(str2):
        return (str1, str2)
    else:
        return (str2, str1)


class QueryManager():
    """Manages creation and execution of queries to the OCLC Classify API.

    Raises:
        DataError: Raised when an invalid title/author query is attempted
        OCLCError: Raised when the query to the API fails

    Returns:
        [str] -- A string of XML data comprising of the Classify response body.
    """
    CLASSIFY_ROOT = 'http://classify.oclc.org/classify2/Classify'

    LOOKUP_IDENTIFIERS = [
        'oclc', # OCLC Number
        'isbn', # ISBN (10 or 13)
        'issn', # ISSN
        'upc',  # UPC (Probably unused)
        'lccn', # LCCN
        'swid', # OCLC Work Identifier
        'stdnbr'# Sandard Number (unclear)
    ]

    def __init__(self, searchType, recID, recType, author, title, start):
        self.searchType = searchType
        self.recID = recID
        self.recType = recType
        self.author = QueryManager.parseString(author)
        self.title = QueryManager.parseString(title)
        self.query = None
        self.start = start

    def generateQueryURL(self):
        """Parses the received data and generates a Classify query based either
        on an identifier (preferred) or an author/title combination.
        """
        if self.searchType == 'identifier':
            self.generateIdentifierURL()
        else:
            self.generateAuthorTitleURL()

    def cleanTitle(self):
        """Removes return and line break characters from the current work's
        title. This allows for better matching and cleaner results.
        """
        self.title = ' '.join(
            self.title\
            .replace('\r', ' ')\
            .replace('\n', ' ')\
            .split()
        )

    def generateAuthorTitleURL(self):
        """Generates an author/title query for Classify.

        Raises:
            DataError: Raised if no author is received, which can cause
            unexpectedly large results to be returned for a query.
        """
        if self.author is None or self.title is None:
            raise DataError('Author and title required for search')

        self.cleanTitle()

        titleAuthorParam = 'title={}&author={}'.format(self.title, self.author)

        self.query = "{}?{}".format(
            QueryManager.CLASSIFY_ROOT,
            titleAuthorParam
        )

        self.addClassifyOptions()

    def generateIdentifierURL(self):
        """Creates a query based of an identifier and its type. If either field
        is missing for this request, default to an author/title search.
        """
        if self.recID is not None and self.recType is not None:
            if self.recType not in QueryManager.LOOKUP_IDENTIFIERS:
                raise DataError(
                    'Unrecognized/invalid identifier type {} recieved'.format(
                        self.recType
                    )
                )
            self.query = "{}?{}={}".format(
                QueryManager.CLASSIFY_ROOT,
                self.recType,
                self.recID
            )
            self.addClassifyOptions()
        else:
            self.generateAuthorTitleURL()

    def addClassifyOptions(self):
        """Adds standard options to the Classify queries. "summary=false"
        indicates that a full set of edition records should be returned with a
        single work response and "maxRecs" controls the upper limit on the
        number of possible editions returned with a work.
        """
        self.query = '{}&summary=false&startRec={}&maxRecs=500'.format(
            self.query, self.start
        )

    def execQuery(self):
        """Executes the constructed query against the OCLC endpoint

        Raises:
            OCLCError: Raised if a non-200 status code is received

        Returns:
            [str] -- A string of XML data comprising of the body of the
            Classify response.
        """
        classifyResp = requests.get(self.query)
        if classifyResp.status_code != 200:
            logger.error('OCLC Classify Request failed')
            raise OCLCError('Failed to reach OCLC Classify Service')

        return classifyResp.text
    
    @classmethod
    def parseString(cls, string):
        if isinstance(string, str):
            cleanString = string.strip()
            return cleanString if cleanString != '' else None
        
        return string
