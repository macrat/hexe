FROM ubuntu:latest

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
        python3 \
        python3-pip \
        python3-dev \
        curl \
        wget \
        git \
        jq \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --upgrade \
        pip \
        bash_kernel

VOLUME /connection_file

CMD ["/usr/bin/python3", "-m", "bash_kernel", "-f", "connection_file"]
