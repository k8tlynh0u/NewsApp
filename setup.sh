# setup.sh

# Create a directory for the keyring if it doesn't exist
mkdir -p -m 755 /etc/apt/keyrings

# Download Google's signing key and store it in the new directory
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg

# Add Google's official software repository to the system's list of sources
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list

# Update the package list to include Google's new repository
apt-get update

# Now, install Google Chrome (and ffmpeg)
apt-get install -y google-chrome-stable ffmpeg
