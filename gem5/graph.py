"""
Consume the output of a testing run, and graph the results.
"""

import json
import matplotlib
matplotlib.use("agg")
import matplotlib.pyplot as plt
# Open the JSON file and parse the contents
with open("result/output.json", "r") as f:
    data = json.load(f)

# Create a figure
fig, ax = plt.subplots()

# Iterate through each experiment in the JSON data
for experiment in data:
    # Extract the injection rates and latencies for this experiment
    injection_rates = [result["injection_rate"] for result in experiment["results"]]
    latencies = [result["packet_latency"] for result in experiment["results"]]

    # Plot the injection rate vs latency data
    ax.plot(injection_rates, latencies, "-x", markersize=4, label="{}-{}-{}".format(
        experiment['experiment']['benchmark'],
        experiment['experiment']['cores'],
        experiment['experiment']['vc']))

# Add a title and labels to the axis
ax.set_title("Injection rate vs latency")
ax.set_xlabel("Injection rate")
ax.set_ylabel("Latency")

# Add a legend
ax.legend()

# Cap the y-axis at 500
ax.set_ylim(0, 500)

plt.savefig("out.png")

