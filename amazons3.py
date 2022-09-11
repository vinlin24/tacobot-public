
"""Handles communication with AWS S3 server."""

from typing import *
from functools import partial
import asyncio

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

import helper

##### LOGGER #####

logger, *funcs = helper.get_logger(__name__, 10)
# Abbreviate print functions
print, printinf, printwar, printerr, printcrt = funcs

##### CLASS WRAPPER #####

class S3Client(object):
	"""Wrapper class for botocore.client.S3 objects."""

	def __init__(self, access_key: str, secret_key: str) -> None:
		self.__client = boto3.client("s3",
									 aws_access_key_id=access_key,
									 aws_secret_access_key=secret_key)
		printinf(f"Created S3Client object with access key {access_key[:4]}{'*'*(len(access_key)-4)}")

	@property
	def client(self) -> "botocore.client.S3":
		return self.__client

	async def upload(self, filename: str, bucketname: str, s3_filename: str, *,
					 loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
		"""
		Uploads a file to AWS S3 bucket named bucketname as s3_filename.
		Returns True if upload was successful, False otherwise.
		"""
		# Handle default arg
		loop = loop or asyncio.get_event_loop()

		try:
			await loop.run_in_executor(None, self.client.upload_file, filename, bucketname, s3_filename)
			printinf(f"Uploaded '{filename}' to '{bucketname}' bucket as '{s3_filename}'")
			return True
		except FileNotFoundError:
			printerr(f"File '{filename}' was not found")
			return False
		except Exception as E:
			printerr(E)
			return False

	async def download(self, s3_filename: str, bucketname: str, filename: str, *,
					   loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
		"""
		Downloads a file from AWS S3 bucket named bucketname to path filename.
		Returns True if upload was successful, False otherwise.
		"""
		# Handle default arg
		loop = loop or asyncio.get_event_loop()

		try:
			await loop.run_in_executor(None, self.client.download_file, bucketname, s3_filename, filename)
			printinf(f"Downloaded '{s3_filename}' from '{bucketname}' bucket as '{filename}'")
			return True
		except FileNotFoundError:
			printerr(f"No such file or directory exists: '{filename}'")
			return False
		except Exception as E:
			printerr(E)
			return False

	async def obj_exists(self, bucketname: str, objectkey: str, *,
						 loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
		"""
		Returns True if objectkey exists inside bucket.
		Returns False if encountered error or objectkey does not exist.
		"""
		# Handle default arg
		loop = loop or asyncio.get_event_loop()

		# Necessary because run_in_executor() does not accept keyword arguments
		func = partial(self.client.list_objects, Bucket=bucketname, Prefix=objectkey)
		try:
			response = await loop.run_in_executor(None, func)
		except Exception as E:
			printerr(E)
			return False

		# response dict has "Contents" key if Prefix exists in Bucket
		return "Contents" in response

	async def create_folder(self, bucketname: str, folderkey: str, *,
							loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
		"""
		Creates a folder with key folderkey in bucket.
		Does nothing if folder already exists.
		Returns whether a new folder was successfully created.
		"""
		# Handle default arg
		loop = loop or asyncio.get_event_loop()

		# Consistent formatting
		folderkey = folderkey + "/" if not folderkey.endswith("/") else folderkey

		if await self.obj_exists(bucketname, folderkey):
			printinf(f"Folder with key {folderkey} already exists in {bucketname} bucket")
			return False

		# Necessary because run_in_executor() does not accept keyword arguments
		func = partial(self.client.put_object, Bucket=bucketname, Body="", Key=folderkey)
		try:
			await loop.run_in_executor(None, func)
		except Exception as E:
			printerr(E)
			return False
		
		printinf(f"Created folder with key {folderkey} in {bucketname} bucket")
		return True

	async def generate_url(self, bucketname: str, objectkey: str, expires_in: int = 3600, *,
						   loop: Optional[asyncio.AbstractEventLoop] = None) -> Optional[str]:
		"""Generate and return a presigned url for an object, None if failed."""
		# Handle default arg
		loop = loop or asyncio.get_event_loop()

		func = partial(self.client.generate_presigned_url,
			ClientMethod="get_object",
			Params={"Bucket": bucketname, "Key": objectkey},
			ExpiresIn=expires_in)

		try:
			url = await loop.run_in_executor(None, func)				
		except Exception as E:
			printerr(E)
			return None

		return url
