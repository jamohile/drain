from cmath import exp
from logging import root
import os
from struct import pack
import subprocess
import json
import multiprocessing
import signal

binary = 'build/Garnet_standalone/gem5.opt'

class RoutingAlgorithm:
	"""
	Abstraction layer over gem5-level routing algorithms.
	These consist of a key, which the simulator uses, and a human-readable name.
	"""
	def __init__(self, key, name):
		self.key = key
		self.name = name

class NetworkConfiguration:
	"""
	A single network topology configuration.
	This contains all settings that are specific to a single network, i.e hardware-level in real life.
	"""
	
	def __init__(self, num_cores, num_rows, mesh_config, spin_config, virtual_channels, routing_algorithm, spin_freq):
		self.num_cores = num_cores
		self.num_rows = num_rows
		self.mesh_config = mesh_config
		self.spin_config = spin_config
		self.virtual_channels = virtual_channels
		self.routing_algorithm = routing_algorithm
		self.spin_freq = spin_freq


class Measurement:
	"""
	A single experimental measured latency, given some injection rate.
	"""
	def __init__(self, injection_rate, packet_latency):
		self.injection_rate = injection_rate
		self.packet_latency = packet_latency
	
	def toDict(self):
		return {"injection_rate": self.injection_rate, "packet_latency": self.packet_latency}

class Experiment:
	"""
	An experiment consists of a single hardware configuration, paired alongside a single software configuration.
	While running an experiment, packet latencies are collection across increasing injection rates.
	"""

	def __init__(self, network_config, benchmark):
		self.network_config = network_config
		self.benchmark = benchmark
		self.measurements = []
	
	def last_packet_latency(self):
		if self.measurements:
			return self.measurements[-1].packet_latency
		else:
			return 0
	
	def add_packet_latency(self, injection_rate, packet_latency):
		self.measurements.append(Measurement(injection_rate, packet_latency))

	def run(self, maximum_packet_latency, cycles, root_output_dir):
			injection_rate = 0

			while self.last_packet_latency() < maximum_packet_latency:
				injection_rate += 0.02

				# Control flags for Gem5.
				flags = [
					"--network=garnet2.0",

					# Physical network topology.
					"--topology=irregularMesh_XY",
					"--num-cpus=%d" 					% self.network_config.num_cores,
					"--num-dirs=%d"  					% self.network_config.num_cores,
					"--mesh-rows=%d"  				% self.network_config.num_rows,
					"--conf-file=" 						+ self.network_config.mesh_config,
					
					# Network-level configuration.
					"--router-latency=1",
					"--uTurn-crossbar=1",
					"--vcs-per-vnet=%d" 			% self.network_config.virtual_channels,
					"--routing-algorithm=%d" 	% self.network_config.routing_algorithm.key,

					# Basic simulation behaviour.
					# The simulated traffic to use, and the length of that traffic to simulate.
					"--synthetic=" 						+ self.benchmark,
					"--sim-cycles=%d" 				% cycles,

					# Drain is built on top of SPIN.
					# Enable spin every freq cycles.
					"--spin=1",
					"--spin-freq=%d" 					% self.network_config.spin_freq,
					# Each spin epoch, this many spins will be performed.
					"--spin-mult=1",
					"--spin-file=" 						+ self.network_config.spin_config,

					# "Indepedent" variable being tested.
					# As we change this injection rate, we should see a change in the latency as the network approaches saturation.
					"--inj-vnet=0",
					"--injectionrate=%1.2f"		% injection_rate,
				]

				output_dir = os.path.join(
					root_output_dir,
					"%s" % self.network_config.num_cores,
					self.network_config.routing_algorithm.name,
					self.benchmark.upper(),
					"freq-%d" 			% self.network_config.spin_freq,
					"vc-%d" 				% self.network_config.virtual_channels,
					"inj-%1.2f" 		% injection_rate
				)

				# Run simulator with provided configuration.
				# The passed configs/ file is the actual gem5 network simulation that will be used,
				# consuming the configuration and traffic we configured above.
				subprocess.call([binary, "-d", output_dir, "configs/example/garnet_synth_traffic.py"] + flags)

				# Scan through the simulator's output, to specificially find the average flit latency.
				_, packet_latency = subprocess.check_output([
					"grep", "system.ruby.network.average_flit_latency", os.path.join(output_dir, "stats.txt"),
				]).split()

				self.add_packet_latency(injection_rate, float(packet_latency))

	def toDict(self):
		return {
			"cores": self.network_config.num_cores,
			"benchmark": self.benchmark.upper(),
			"vc": self.network_config.virtual_channels,

			"measurements": [m.toDict() for m in self.measurements]
		}

# A number of different routing algorithms are supported.
# These correspond to the settings used within Gem5.
routing_algorithms = {
	"ADAPT_RAND_": RoutingAlgorithm(0, "ADAPT_RAND_"),
	"UP_DN_": RoutingAlgorithm(1, "UP_DN_"),
	"Escape_VC_UP_DN_": RoutingAlgorithm(2, "Escape_VC_UP_DN_"),
}

# Entirely user-set network configurations to test against.
# These can be modified as required..
network_configurations = [
	NetworkConfiguration(
		num_cores=64,
		num_rows=8,
		mesh_config="64_nodes-connectivity_matrix_0-links_removed_0.txt",
		spin_config="spin_configs/SR_64_nodes-connectivity_matrix_0-links_removed_0.txt",
		routing_algorithm=routing_algorithms["ADAPT_RAND_"],
		virtual_channels=4,
		spin_freq=1024

	),

	NetworkConfiguration(
		num_cores=256,
    num_rows=16,
		mesh_config="256_nodes-connectivity_matrix_0-links_removed_0.txt",
		spin_config="spin_configs/SR_256_nodes-connectivity_matrix_0-links_removed_0.txt",
		routing_algorithm=routing_algorithms["ADAPT_RAND_"],
		virtual_channels=4,
		spin_freq=1024
	)
]

# Specific Gem5 benchmarks we are interested in testing against.
# These can be changed, but must be valid.
benchmarks=[ "bit_rotation", "shuffle", "transpose" ]

def run_experiment(experiment):
	experiment.run(maximum_packet_latency=200.0, cycles=1e5, root_output_dir="./results")
	return experiment

def main():
	# Build simulator.
	# os.system("scons -j15 {}".format(binary))

	# Clean up any leftover outputs.
	subprocess.call('rm -rf ./results', shell=True)
	subprocess.call('mkdir results', shell=True)

	# Prepare experiments.
	experiments = []
	for network_config in network_configurations:
		for benchmark in benchmarks:
			experiments.append(Experiment(network_config, benchmark))
	
	# Run all experiments using multithreading.
	# Note, this is a bit messy, but it is up to the experiments to make sure they do not write to the same locations.

	pool = multiprocessing.Pool()
	results = pool.map(run_experiment, experiments)
	print("Done all experiments.")

	print(results)

	# Print all results.
	print(json.dumps([experiment.toDict() for experiment in experiments], indent=2))

main()