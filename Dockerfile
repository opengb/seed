# VERSION 0.1
# AUTHOR:           Clay Teeter <teeterc@gmail.com>, Nicholas Long <nicholas.long@nrel.gov>
# DESCRIPTION:      Image with seed platform and dependencies running in development mode
# TO_BUILD_AND_RUN: docker-compose build && docker-compose up

# Latest Ubuntu LTS
FROM ubuntu:16.10

### Required dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential                                          \
        vim                                                      \
        git                                                      \
        libpcre3                                                 \
        libpcre3-dev

### Development Dependencies
##        emacs24-nox \
##        swig \
##        libssl-dev \
##        liblzma-dev \
##        libevent1-dev \
##        mercurial \
##        libpq-dev \
##        enchant \

### Install JavaScript requirements
RUN apt-get install -y --no-install-recommends \
        npm \
        nodejs

### link the apt install of nodejs to node (expected by bower)
RUN ln -s /usr/bin/nodejs /usr/bin/node

COPY ./bower.json /seed/bower.json
COPY ./.bowerrc /seed/.bowerrc
COPY ./package.json /seed/package.json
# stops the no readme warning
COPY ./README.md /seed/README.md
RUN npm update
COPY ./bin/install_javascript_dependencies.sh /seed/bin/install_javascript_dependencies.sh
RUN /seed/bin/install_javascript_dependencies.sh

### Install python requirements
RUN apt-get install -y --no-install-recommends \
        python2.7                              \
        python-pip                             \
        python-dev                             \
        python-gdbm                            \
        python-scipy                           \
        python-numpy                           \
        enchant                                \
    && pip install --upgrade pip               \
    && pip install setuptools

WORKDIR /seed
COPY ./requirements.txt /seed/requirements.txt
COPY ./requirements/*.txt /seed/requirements/
RUN pip install -r requirements/local.txt

RUN rm -rf /var/lib/apt/lists/*

### Copy over the remaining part of the SEED application and some helpers
COPY . /seed/
COPY ./docker/wait-for-it.sh /usr/local/wait-for-it.sh
COPY ./config/settings/local_untracked_docker.py /seed/config/settings/local_untracked.py

EXPOSE 8000
