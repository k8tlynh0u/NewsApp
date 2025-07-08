# setup.sh (FINAL, COMMUNITY-TESTED VERSION)
# This script is designed to install all necessary dependencies for
# both Google Chrome and the Chromedriver on Streamlit Cloud's Debian environment.

# Update package lists
apt-get update

# Install essential packages that chromedriver depends on
apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxshmfence1 \
    libxtst6 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    libxrandr2 \
    libcups2 \
    at-spi2-core \
    lsb-release \
    xdg-utils \
    ffmpeg

# Download and install the latest stable version of Google Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -i google-chrome-stable_current_amd64.deb || apt-get -f install -y

# Clean up the downloaded deb file
rm google-chrome-stable_current_amd64.deb
