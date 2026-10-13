#!/bin/bash

for file in */ ; do 
  if [[ -d "$file" && ! -L "$file" ]]; then
    pushd $file
      echo "Scanning $file"; 
      semgrep scan --config auto
      echo "Scanning Done"; 
    popd
  fi; 
done
