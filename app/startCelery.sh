#!/bin/bash

celery -A chaotica worker --beat --scheduler django --loglevel=info
