FROM ubuntu:latest

WORKDIR /app

# Copy the current directory into the container at /app
COPY . /app

# Install necessary packages
RUN apt-get update && apt-get install -y \
    # Building Camoufox for Windows requires Wine,
    # which requires /lib/ld-linux.so.2,
    # which is provided by libc6-i386.
    libc6-i386 \
    # Mach build tools
    build-essential make msitools wget unzip rustc \
    # Python
    python3 python3-dev python3-pip \
    # Camoufox build system tools
    git p7zip-full aria2 curl rsync \
    # Keep a cache available when bootstrap does not install sccache.
    ccache \
    # Platform-specific libraries for Linux builds
    libsqlite3-dev \
    # CA certificates
    ca-certificates \
    && update-ca-certificates

RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Fetch Firefox & apply initial patches
RUN make setup-minimal && \
    make mozbootstrap && \
    mkdir -p /app/dist

# Keep compiler caches on the mounted .mozbuild volume instead of the
# container's disposable root filesystem.
ENV CCACHE_DIR=/root/.mozbuild/ccache \
    SCCACHE_DIR=/root/.mozbuild/sccache-cache \
    CAMOUFOX_SCCACHE=1

# Mount .mozbuild directory and dist folder
VOLUME /root/.mozbuild
VOLUME /app/dist

ENTRYPOINT ["python3", "./multibuild.py"]
