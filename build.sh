#!/bin/bash
set -e

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Chrome and ChromeDriver..."

# تحديث النظام
apt-get update

# تثبيت Chromium و ChromeDriver
apt-get install -y chromium chromium-driver

# أو تجربة Chrome بدلاً من Chromium
# wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
# echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list
# apt-get update
# apt-get install -y google-chrome-stable

echo "Build completed successfully!"
