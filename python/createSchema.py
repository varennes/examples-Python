# This script generates a JSON schema for a given data file to be used with the 'bq load' command line tool.
# -------------------------------------------------------------

import sys
import string
import gzip
from dateutil.parser import parse
# -------------------------------------------------------------

# INPUT: path to local data file
# OUTPUT: JSON schema to stdout
# BigQuery data types = ['string','bytes','integer','float','boolean','record','timestamp']
# BigQuery modes = ['nullable','required','repeated'] , default is nullable
# -------------------------------------------------------------

# function to check is a given value is numeric
def isNumeric(val):
    try:
        float(val)
        return True
    except ValueError:
        return False

# --------------------------------------------------------------

specialChars = [ ' ', '-', ')', '(', ',', ':', ';', '.', '@', 
                 '#', '$', '%', '^', '&', '*', '[', ']', '{', 
                 '}', '|', '/', '?' ]

def removeSpecialChars ( aString ):

    bString = ''
    for ii in range(len(aString)):
        if ( aString[ii] in specialChars ):
            if ( bString[-1] != "-" ): bString += '_'
        else:
            bString += aString[ii]

    if ( bString[-1] == "_" ): bString = bString[:-1]

    return ( bString )

# --------------------------------------------------------------

def letter_or_underscore ( aChar ):

    io = ord(aChar)
    if ( io == 95 ): return ( 1 )
    if ( io>=64 and io<=90 ): return ( 1 )
    if ( io>=97 and io<=122 ): return ( 1 )
    return ( 0 )

# --------------------------------------------------------------

def valid_char ( aChar ):

    io = ord(aChar)
    if ( io == 95 ): return ( 1 )
    if ( io>=48 and io<=57 ): return ( 1 )
    if ( io>=64 and io<=90 ): return ( 1 )
    if ( io>=97 and io<=122 ): return ( 1 )
    return ( 0 )

# --------------------------------------------------------------

def createValidBQfieldName ( aString ):

    ## print " "
    ## print " in createValidBQfieldName ... <%s> " % aString

    bString = removeSpecialChars ( aString )
    ## print " <%s> " % bString

    ## make sure that the following is satisfied:
    ## Fields must contain only letters, numbers, and underscores, start
    ## with a letter or underscore, and be at most 128 characters long.

    if ( len(bString) > 128 ): 
        cString = createValidBQfieldName ( bString[:128] )
    else:
        cString = bString

    ## check first character:
    ## print " <%s> " % cString
    if not letter_or_underscore ( cString[0] ):
        print " createValidBQfieldName: first character is not valid <%s> " % cString
        sys.exit(-1)

    ## check all other characters:
    for ii in range(len(cString)):
        if not valid_char ( cString[ii] ):
            print " createValidBQfieldName: invalid character at position %d <%s> " % ( ii, cString )
            sys.exit(-1)

    return ( cString )

# --------------------------------------------------------------

def inferDataTypes ( dataRow, dataTypes ):

    for ii in range(len(dataRow)):

        item = dataRow[ii].strip()

        if ( item == '' ):
            ## print " SKIPPING field #%d because it is blank ... " % ii      
            continue

        elif ( dataTypes[ii] == "string" ):
            ## print " SKIPPING field #%d because it is already a STRING " % ii
            continue

        elif ( item.lower()=="true" or item.lower()=="false" ):
            if ( dataTypes[ii] == "NA" ):
                print " initially setting field #%d to BOOLEAN (%s) " % ( ii, item )
                dataTypes[ii] = "boolean"
            elif ( dataTypes[ii] == "boolean" ):
                continue
            else: 
                print " ERROR ??? conflicting data types ??? ", item, dataTypes[ii]
                dataTypes[ii] = "string"

        else:

            try:
                iVal = int(item)
                if ( dataTypes[ii] == "NA" ):
                    print " initially setting field #%d to INTEGER (%s) " % ( ii, item )
                    dataTypes[ii] = "integer"
                elif ( dataTypes[ii] == "integer" ):
                    continue
                elif ( dataTypes[ii] == "float" ):
                    continue
                else:
                    print " ERROR ??? conflicting data types ??? ", item, dataTypes[ii]
                    dataTypes[ii] = "string"

            except:
                try:
                    fVal = float(item)
                    if ( dataTypes[ii] == "NA" ):
                        print " initially setting field #%d to FLOAT (%s) " % ( ii, item )
                        dataTypes[ii] = "float"
                    elif ( dataTypes[ii] == "float" ):
                        continue
                    elif ( dataTypes[ii] == "integer" ):
                        print " CHANGING field #%d from INTEGER to FLOAT (%s) " % ( ii, item )
                        dataTypes[ii] = "float"
                        continue
                    else:
                        print " ERROR ??? conflicting data types ??? ", item, dataTypes[ii]
                        dataTypes[ii] = "string"

                except:
                    if ( dataTypes[ii] == "NA" ):
                        print " initially setting field #%d to STRING (%s) " % ( ii, item )
                    else:
                        print " CHANGING field #%d to STRING (%s) " % ( ii, item )
                    dataTypes[ii] = "string"

    ## print dataTypes
    return ( dataTypes )
        
# --------------------------------------------------------------

inFilename = sys.argv[1]
dmpFh = file ( "subsample.tsv", 'w' )

# open data file ...
try:
    if inFilename.endswith('gz'):
        dataFile = gzip.open(inFilename,"r")
    else:
        dataFile = open(inFilename,"r")
except:
    print 'requires input filename as command-line parameter'
    if ( len(inFilename) > 0 ):
        print ' --> failed to open <%s> ' % inFilename
    sys.exit()

print " "
print "Parsing input file <%s>." % inFilename
print " "

# first line is expected to be the header
aLine = dataFile.readline()
dmpFh.write ( '%s' % aLine )
headerRow = aLine.split('\t')

# if any numeric values in this first line, it is likely not a header: hence exit
if any([isNumeric(x) for x in headerRow]):
    print 'Numeric fields found in the first line. Perhaps the header is missing. Please check input file.'
    print headerRow
    sys.exit()

# build up a list of field names based on the header tokens and make sure they
# are all unique
fieldNames = []
lowerNames = []
for ii in range(len(headerRow)):
    aName = removeSpecialChars ( headerRow[ii].strip() )
    aName = createValidBQfieldName ( headerRow[ii].strip() )
    if ( aName.lower() in lowerNames ):
        print " ERROR: repeated header token <%s> " % aName
        sys.exit(-1)
    elif ( aName == "" ):
        print " ERROR: blank header token ??? "
        sys.exit(-1)
    else:
        fieldNames += [ aName ]
        lowerNames += [ aName.lower() ]

print " "
print fieldNames
print " "

dataTypes = ['NA' ] * len(fieldNames)

## this is the # of lines that we'll skip over each time we
## read and parse a single line of data ...
nSkip = 1000

done = 0
while not done:

    # next, read a data row to infer column data types
    aLine = dataFile.readline()
    dmpFh.write ( '%s' % aLine )
    dataRow = aLine.split('\t')
    if ( len(dataRow) == 1 ):
        done = 1
        continue

    if ( len(dataRow) != len(fieldNames) ):
        print " ERROR ??? # of values in data row is not as expected ??? ", len(dataRow), len(fieldNames)
        print " "
        for ii in range(min(len(dataRow),len(fieldNames))):
            print " %3d  %s  %s " % ( ii, fieldNames[ii], dataRow[ii] )
        sys.exit(-1)

    dataTypes = inferDataTypes ( dataRow, dataTypes )

    ## skip over a bunch of rows, we don't want to check every single row,
    ## just a few of them at random ...
    for jj in range(nSkip):
        dataRow = dataFile.readline()
        if ( len(dataRow) < 1 ): done = 1

dataFile.close()
dmpFh.close()

schemaFilename = inFilename + ".json"
try:
    fhOut = file ( schemaFilename, 'w' )
except:
    print " ERROR??? failed to open output schema file??? "
    print schemaFilename
    sys.exit(-1)

print " "
print " "
print "writing draft JSON schema to <%s> " % schemaFilename
print " "

# print opening bracket
fhOut.write ( '[\n' )

#  the available data types are described in detail at: https://cloud.google.com/bigquery/data-types
#  and include: STRING, BYTES, INTEGER, FLOAT, BOOLEAN ('true' or 'false'),
#  RECORD, and TIMESTAMP
#  here we will only try to infer STRING, INTEGER, FLOAT, or BOOLEAN

# loop through the columns
for ii in range(len(fieldNames)):

    # in case we got this far w/o a dataType getting set ...
    if ( dataTypes[ii] == "NA" ):
        dataTypes[ii] = "string"

    outStr = '    {"name": "'+fieldNames[ii]+'", "type": "'+dataTypes[ii]+'", "mode": "nullable", "description": "<add description here>"}'
    if ( ii < len(fieldNames)-1 ):
        outStr+=','

    fhOut.write ( '%s\n' % outStr )

# print closing bracket
fhOut.write ( ']\n' )

fhOut.close()

