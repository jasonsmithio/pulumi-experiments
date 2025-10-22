#!/bin/bash

echo "starting the server"
# start the server. By default torchserve runs in backaround, and start.sh will immediately terminate when done
# so use --foreground to keep torchserve running in foreground while start.sh is running in a container  
torchserve --start --ts-config config.properties --models "stable_diffusion=${MAR_FILE_NAME}.mar" --model-store ${MAR_STORE_PATH} --foreground