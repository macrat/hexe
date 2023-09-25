.PHONY: check start fmt

check:
	pipenv run mypy *.py

start:
	pipenv run uvicorn main:app --reload

fmt:
	pipenv run black *.py
