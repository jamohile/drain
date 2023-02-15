FROM ubuntu:bionic

# Install Python
RUN apt-get update
RUN apt-get install -y python2.7
RUN ln -s /usr/bin/python2.7 /usr/bin/python
RUN apt-get install -y python-pip

# Install other system dependencies.
RUN apt-get install -y zlib1g-dev
RUN apt-get install -y libgoogle-perftools-dev
RUN apt-get install -y m4

# Tools to help.
RUN apt-get install -y htop

# Install Scons
RUN python -m pip install scons