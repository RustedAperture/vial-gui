FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git wget curl ca-certificates xz-utils bzip2 perl python3 python-is-python3 python3-venv python3-pip \
    pkg-config cmake ninja-build zlib1g-dev libffi-dev libssl-dev libbz2-dev liblzma-dev \
    libgl1-mesa-dev gperf bison flex patch file unzip openjdk-11-jre-headless \
    && rm -rf /var/lib/apt/lists/*
