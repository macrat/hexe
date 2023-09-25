FROM ubuntu:latest

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
        python3 \
        python3-pip \
        python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && /usr/bin/python3 -m pip install --upgrade \
        pip \
        ipython \
        ipykernel \
        beautifulsoup4 \
        lxml \
        matplotlib \
        numpy \
        pandas \
        pyppeteer \
        pyquery \
        pyyaml \
        requests \
        requests-html \
        scikit-learn \
        scipy \
        seaborn

VOLUME /connection_file

CMD ["/usr/bin/python3", "-m", "ipykernel_launcher", "-f", "connection_file"]
