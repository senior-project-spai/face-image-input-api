# FastAPI
from fastapi import FastAPI, File, Form, UploadFile
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# SQL
import pymysql

# S3
import boto3
from botocore import UNSIGNED
from botocore.client import Config

# Kafka
from kafka import KafkaProducer
from json import dumps

import os  # environment variable

# logging
import logging
logger = logging.getLogger("api")

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=['*'])


@app.on_event('startup')
def startup_event():
    global kafka_producer
    kafka_producer = KafkaProducer(bootstrap_servers=['{0}:{1}'.format(
        os.getenv('KAFKA_HOST'), os.getenv('KAFKA_PORT'))])


@app.on_event('shutdown')
def shutdown_event():
    sql_connection.close()


class FaceImageInputResponseModel(BaseModel):
    face_image_id: int

@app.post("/_api/face", response_model=FaceImageInputResponseModel)
def face_image_input(image: UploadFile = File(...),  # ... = required
                     image_name: str = Form(...),
                     branch_id: int = Form(...),
                     camera_id: int = Form(...),
                     time: int = Form(...),
                     position_top: int = Form(None),  # None = not required
                     position_right: int = Form(None),
                     position_bottom: int = Form(None),
                     position_left: int = Form(None)):

    # Upload image to S3
    s3_resource = boto3.resource('s3',
                                 endpoint_url=os.getenv('S3_ENDPOINT'),
                                 aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
                                 aws_secret_access_key=os.getenv(
                                     'S3_SECRET_KEY'),
                                 config=Config(signature_version='s3v4'))
    bucket_name = os.getenv('S3_BUCKET')
    bucket = s3_resource.Bucket(bucket_name)
    bucket.upload_fileobj(image.file, image_name)
    image_s3_uri = "s3://{0}/{1}".format(bucket_name, image_name)
    logger.debug("image_s3_uri = {}".format(image_s3_uri))

    # Insert data to SQL
    sql_connection = pymysql.connect(host=os.getenv('MYSQL_MASTER_HOST'),
                                     port=int(os.getenv('MYSQL_MASTER_PORT')),
                                     user=os.getenv('MYSQL_MASTER_USER'),
                                     passwd=os.getenv('MYSQL_MASTER_PASS'),
                                     db=os.getenv('MYSQL_MASTER_DB'))
    image_id = None
    with sql_connection.cursor() as cursor:
        insert_sql = ("INSERT INTO `FaceImage` (`image_path`, `camera_id`, `branch_id`, `time`, `position_top`, `position_right`, `position_bottom`, `position_left`) "
                      "VALUES (%(image_path)s, %(camera_id)s, %(branch_id)s, %(time)s, %(position_top)s, %(position_right)s, %(position_bottom)s, %(position_left)s)")
        cursor.execute(insert_sql, {'image_path': image_s3_uri,
                                    'camera_id': camera_id,
                                    'branch_id': branch_id,
                                    'time': time,
                                    'position_top': position_top,
                                    'position_right': position_right,
                                    'position_bottom': position_bottom,
                                    'position_left': position_left})
        sql_connection.commit()  # commit changes
        image_id = cursor.lastrowid  # get last inserted row id
    # Send data to Kafka
    obj = {'face_image_id': image_id,
           'face_image_path': image_s3_uri,
           'position_top': position_top,
           'position_right': position_right,
           'position_bottom': position_bottom,
           'position_left': position_left}
    kafka_producer.send(os.getenv('KAFKA_TOPIC_FACE_IMAGE'),
                        value=dumps(obj).encode(encoding='UTF-8'))
    
    sql_connection.close()
    # Return ID to response
    return {'face_image_id': image_id}
