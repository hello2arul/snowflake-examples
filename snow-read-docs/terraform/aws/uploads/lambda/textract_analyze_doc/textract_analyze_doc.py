import boto3
import botocore
import time
import json
import os
from collections import defaultdict
import logging
import logging.config
from urllib.parse import unquote_plus
from datetime import datetime
from trp import Document

###############################################################################
# AWS Lamda to read input event from S3 and to make textract call to analyze doc
#
# - Created by Siva Nadesan on 2023/03/18
# - Modified by Siva Nadesan on 2023/03/18
#
###############################################################################

# Logging
logging.config.fileConfig(fname='log.conf')
logger = logging.getLogger(__name__)

# Initialize s3 connection
environment_code = os.environ.get('ENVIRONMENT_CODE', 'temp')
logger.info('Environment Code ~ {}'.format(environment_code))

# Initialize boto client for s3
if environment_code in ('local'):
    s3 = boto3.resource(
        's3', endpoint_url='http://host.docker.internal:4566', use_ssl=False)
else:
    s3 = boto3.resource('s3')


def lambda_handler(event, context):
    """
    Process incoming events
    """

    # Log the function name
    logger.info('Function Name ~ {}'.format(context.function_name))
    logger.info('Event Details ~ {}'.format(event))

    # 200 is the HTTP status code for "ok".
    status_code = 200

    # Initialize response
    response_to_return = {}

    # # Loops through every event / S3 Event
    # for record in event['Records']:

    # Loops through every event / SNS Event
    for event_record in event['Records']:
        logger.info('SNS ~ {}'.format(event_record['Sns']))
        logger.info('Message ~ {}'.format(event_record['Sns']['Message']))
        logger.info('SNS Record ~ {}'.format(json.loads(
            event_record['Sns']['Message'])['Records']))
        for record in json.loads(event_record['Sns']['Message'])['Records']:

            # Log input payload
            logger.info('Input payload ~ {}'.format(record))

            # Get s3 details from the event trigger/S3 event
            # s3_bucket_region = record['awsRegion']
            # s3_bucket_name = record['s3']['bucket']['name']
            # s3_object_name = unquote_plus(record['s3']['object']['key'])

            # Get s3 details from the event trigger/SNS event
            s3_bucket_region = 'us-east-1'
            s3_bucket_name = record['s3']['bucket']['name']
            s3_object_name = record['s3']['object']['key']

            # Log parsed input variables
            logger.info('s3_bucket_region ~ {}'.format(s3_bucket_region))
            logger.info('s3_bucket_name ~ {}'.format(s3_bucket_name))
            logger.info('s3_object_name ~ {}'.format(s3_object_name))

            # Initialize boto client for textract
            client = boto3.client('textract', region_name=s3_bucket_region)

            try:
                # Analyze TABLES | FORMS | QUERIES | SIGNATURES
                response = None
                response, response_parsed = perform_analyze_document(
                    client, s3_bucket_name, s3_object_name, feature_types=['FORMS', 'TABLES'])

                write_response_to_s3(
                    s3_bucket_name, s3_object_name, response, type='raw')

                write_response_to_s3(
                    s3_bucket_name, s3_object_name, response_parsed, type='parsed')

                response_to_return = {
                    "objectKey": s3_object_name, "status": "SUCCESS"}

            except Exception as err:
                logger.warn('Input error ~ {}'.format(err))
                # 400 implies some type of error.
                status_code = 400
                # Tell caller what this function could not handle.
                response_to_return = record

    # Return the return value and HTTP status code.
    return {
        'statusCode': status_code,
        'body': response_to_return
    }


def perform_analyze_document(client, s3_bucket_name, s3_object_name, feature_types):

    # Analyze TABLES | FORMS | QUERIES | SIGNATURES
    response = client.analyze_document(Document={'S3Object': {
        'Bucket': s3_bucket_name, 'Name': s3_object_name}}, FeatureTypes=feature_types)
    doc = Document(response)

    response_parsed = []
    response_forms = {}
    response_forms["forms"] = {}

    response_tables = {}
    response_tables["tables"] = {}

    # Logic to read FORMS (key/value pair) from the document
    for page in doc.pages:

        for field in page.form.fields:
            response_forms["forms"][str(field.key)] = str(field.value)

    # Add FORMS response to response array
    response_parsed.append(response_forms)

    # Logic to read TABLES from the document
    for page in doc.pages:

        table_count = 0
        for table in page.tables:
            response_tables["tables"]["table_" + str(table_count)] = {}
            for r, row in enumerate(table.rows):
                response_tables["tables"]["table_" +
                                          str(table_count)]["row_" + str(r)] = {}
                for c, cell in enumerate(row.cells):
                    response_tables["tables"]["table_" + str(table_count)]["row_" + str(
                        r)]["column_" + str(c)] = str(cell.text)

            table_count = table_count + 1

    # Add TABLES response to response array
    response_parsed.append(response_tables)

    return response, response_parsed


def write_response_to_s3(s3_bucket_name, s3_object_name, data, type):

    # Generate output file name
    output_s3_object_name = generate_output_name(s3_object_name, type)

    # Write back to S3 with the new file name
    try:
        s3.Bucket(s3_bucket_name).put_object(Key=output_s3_object_name, Body=(
            bytes(json.dumps(data).encode('UTF-8'))))
        logger.info('Target S3 Record Key ~ {}'.format(output_s3_object_name))
    except botocore.exceptions.ClientError as err:
        logging.error('S3 write to bucket {} with for key {} failed. {} '.format(
            s3_bucket_name, output_s3_object_name, err))

    return None


def generate_output_name(s3_object_name, type):

    valid_file_formats = [".PDF", ".TIFF", ".JPG",
                          ".PNG", ".pdf", ".tiff", ".jpg", ".png"]

    s3_object_name = s3_object_name.split('/')[-1]

    for valid_file_format in valid_file_formats:
        s3_object_name = s3_object_name.replace(
            valid_file_format, "_analyze_text_"+type+"_response.json")

    output_dir_prefix = 'textract/response/' + \
        datetime.today().strftime('%Y-%m-%d') + '/' + type + '/' + \
        s3_object_name

    return output_dir_prefix
