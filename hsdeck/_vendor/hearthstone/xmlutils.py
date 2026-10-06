# LOCAL MODIFICATION: `import requests` moved inside the function that needs
# it.  hsdeck always parses CardDefs.xml from a local path, so the download
# path is never taken and the vendored tree must not require a third-party
# package at import time.


class RetryException(Exception):
	pass


def download_to_tempfile(url: str, fp) -> bool:
	import requests

	try:
		with requests.get(url, stream=True) as r:
			if r.ok:
				for chunk in r.iter_content(chunk_size=8192):
					fp.write(chunk)

				return True
			elif 500 <= r.status_code < 600:
				raise RetryException()
			else:
				return False
	except requests.exceptions.RequestException:
		raise RetryException()


def download_to_tempfile_retry(url: str, fp, retries: int = 3) -> bool:
	assert retries >= 0

	try:
		return download_to_tempfile(url, fp)
	except RetryException:
		if retries:
			return download_to_tempfile_retry(url, fp, retries - 1)

		return False
