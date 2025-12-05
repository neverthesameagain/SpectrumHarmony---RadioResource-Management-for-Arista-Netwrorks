# Sensing Orchestra

## How it works
- Gets information about whether the signal is wifi or non wifi from the non wifi classifier
- The MAB algorithm runs to select the noisiest channel and changes the dwell time for each of the channel based on their reward
- The scanning of these channels update the channels parameters whcih in turn updates their rewards
- The scanning is done for both 2.4 and 5 Ghz seperately and in parallel
- Also checks for DFS channels and follows the regulatory conditions
- Also ensures the airtime loss due to scan time is < 2%

## How to run the SensingOrchestra
```bash
# This file is the main file
python3 SensingOrchestra.py
