# FastAPI
from fastapi import FastAPI, File, Form, UploadFile
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# SQL
import mysql.connector

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

# import time
import time as time1

logger = logging.getLogger("api")

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=['*'])

config = {
    'host': os.getenv('MYSQL_MASTER_HOST'),
    'port': int(os.getenv('MYSQL_MASTER_PORT')),
    'user': os.getenv('MYSQL_MASTER_USER'),
    'password': os.getenv('MYSQL_MASTER_PASS'),
    'database': os.getenv('MYSQL_MASTER_DB')
}

pool = mysql.connector.connect(pool_name="mypool",
                               pool_size=2,
                               **config)


class FaceImageInputResponseModel(BaseModel):
    face_image_id: int


@app.post("/_api/face", response_model=FaceImageInputResponseModel)
def face_image_input(image: UploadFile = File(...),  # ... = required
                     image_name: str = Form(...),
                     branch_id: int = Form(...),
                     camera_id: int = Form(...),
                     time: float = Form(...),
                     position_top: int = Form(None),  # None = not required
                     position_right: int = Form(None),
                     position_bottom: int = Form(None),
                     position_left: int = Form(None)):

    # Insert data to SQL
    sql_connection = pool.get_connection()
    image_id = None

    bucket_name = os.getenv('S3_BUCKET')
    image_s3_uri = "s3://{0}/{1}".format(bucket_name, image_name)
    with sql_connection.cursor() as cursor:
        insert_sql = ("INSERT INTO `FaceImage` (`image_path`, `camera_id`, `branch_id`, `image_time`, `position_top`, `position_right`, `position_bottom`, `position_left`, `time`) "
                      "VALUES (%(image_path)s, %(camera_id)s, %(branch_id)s, %(image_time)s, %(position_top)s, %(position_right)s, %(position_bottom)s, %(position_left)s, %(time)s)")
        cursor.execute(insert_sql, {'image_path': image_s3_uri,
                                    'camera_id': camera_id,
                                    'branch_id': branch_id,
                                    'image_time': time,
                                    'position_top': position_top,
                                    'position_right': position_right,
                                    'position_bottom': position_bottom,
                                    'position_left': position_left,
                                    'time': int(round(time1.time() * 1000))/1000})
        sql_connection.commit()  # commit changes
        image_id = cursor.lastrowid  # get last inserted row id
    # sql_connection.close()
    sql_connection.close()
    # Upload image to S3
    s3_resource = boto3.resource('s3',
                                 endpoint_url=os.getenv('S3_ENDPOINT'),
                                 aws_access_key_id=os.getenv(
                                     'S3_ACCESS_KEY'),
                                 aws_secret_access_key=os.getenv(
                                     'S3_SECRET_KEY'),
                                 config=Config(signature_version='s3v4'))
    bucket = s3_resource.Bucket(bucket_name)
    bucket.upload_fileobj(image.file, image_name)
    logger.debug("image_s3_uri = {}".format(image_s3_uri))

    # Send data to Kafka
    obj = {'face_image_id': image_id,
           'face_image_path': image_s3_uri,
           'position_top': position_top,
           'position_right': position_right,
           'position_bottom': position_bottom,
           'position_left': position_left}

    kafka_producer = KafkaProducer(bootstrap_servers=['{0}:{1}'.format(
        os.getenv('KAFKA_HOST'), os.getenv('KAFKA_PORT'))])
    kafka_producer.send(os.getenv('KAFKA_TOPIC_FACE_IMAGE'),
                        value=dumps(obj).encode(encoding='UTF-8'))

    # Return ID to response
    return {'face_image_id': image_id}
