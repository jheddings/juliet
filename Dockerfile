FROM python:3.8

## update python libraries and install common dependencies
RUN python3 -m pip install --upgrade pip
COPY requirements.txt /tmp/
RUN python3 -m pip install -r /tmp/requirements.txt
RUN python3 -m pip cache purge

## set up the application
WORKDIR "/opt"

ENTRYPOINT ["/usr/local/bin/python3"]
CMD ["juliet.py"]

