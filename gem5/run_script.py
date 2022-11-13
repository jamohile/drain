import os
import subprocess

# import pdb; pdb.set_trace()
# first compile then run
binary = 'build/Garnet_standalone/gem5.opt'
os.system("scons -j15 {}".format(binary))

class RoutingAlgorithm:
	def __init__(self, key, name):
		self.key = key
		self.name = name

class RoutingAlgorithms:
	ADAPT_RAND_ = RoutingAlgorithm(0, "ADAPT_RAND_")
	UP_DN_ = RoutingAlgorithm(1, "UP_DN_")
	Escape_VC_UP_DN_ = RoutingAlgorithm(2, "Escape_VC_UP_DN_")

# A single network topology configuration.
class NetworkConfiguration:
	def __init__(self, num_cores, num_rows, mesh_config, spin_config, virtual_channels, routing_algorithm, spin_freq):
		self.num_cores = num_cores
		self.num_rows = num_rows
		self.mesh_config = mesh_config
		self.spin_config = spin_config
		self.virtual_channels = virtual_channels
		self.routing_algorithm = routing_algorithm
		self.spin_freq = spin_freq

network_configurations = [
	NetworkConfiguration(
		num_cores=64,
		num_rows=8,
		mesh_config="64_nodes-connectivity_matrix_0-links_removed_0.txt",
		spin_config="spin_configs/SR_64_nodes-connectivity_matrix_0-links_removed_0.txt",
		routing_algorithm=RoutingAlgorithms.ADAPT_RAND_,
		virtual_channels=4,
		spin_freq=1024

	),

	NetworkConfiguration(
		num_cores=256,
    num_rows=16,
		mesh_config="256_nodes-connectivity_matrix_0-links_removed_0.txt",
		spin_config="spin_configs/256_nodes-connectivity_matrix_0-links_removed_0.txt",
		routing_algorithm=RoutingAlgorithms.ADAPT_RAND_,
		virtual_channels=4,
		spin_freq=1024
	)
]

benchmarks=[ "bit_rotation", "shuffle", "transpose" ]

class Measurement:
	def __init__(self, injection_rate, packet_latency):
		self.injection_rate = injection_rate
		self.packet_latency = packet_latency

class Result:
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

out_dir = './results'
cycles = 100000

os.system('rm -rf ./results')
os.system('mkdir results')

def get_output_dir(network_config, benchmark, injection_rate):
	path = [
		out_dir,
		"%s" % network_config.num_cores,
		network_config.routing_algorithm.name,
		benchmark.upper(),
		"freq-%d" 	% network_config.spin_freq,
		"vc-%d" 		% network_config.virtual_channels,
		"inj-%d" 		% injection_rate
	]

	return "/".join(path)

results = []

for network_config in network_configurations:
	for benchmark in benchmarks:
		print ("cores: {2:d} b: {0:s} vc-{1:d}".format(benchmark.upper(), network_config.virtual_channels, network_config.num_cores))
		injection_rate = 0.02

		result = Result(network_config, benchmark)

		while result.last_packet_latency() < 200.0:
			# Control flags for Gem5.
			flags = " ".join([
				"--topology=irregularMesh_XY",
				"--network=garnet2.0",
				"--router-latency=1",
				"--spin=1",
				"--spin-mult=1",
				"--uTurn-crossbar=1",
				"--inj-vnet=0",
				"--synthetic=" 						+ benchmark,
				"--spin-file=" 						+ network_config.spin_config,
				"--conf-file=" 						+ network_config.mesh_config,
				"--sim-cycles=%d" 				% cycles,
				"--num-cpus=%d" 					% network_config.num_cores,
				"--num-dirs=%d"  					% network_config.num_cores,
				"--mesh-rows=%d"  				% network_config.num_rows,
				"--spin-freq=%d" 					% network_config.spin_freq,
				"--vcs-per-vnet=%d" 			% network_config.virtual_channels,
				"--injectionrate=%1.2f"		% injection_rate,
				"--routing-algorithm=%d" 	% network_config.routing_algorithm.key,
			])

			output_dir = get_output_dir(network_config, benchmark, injection_rate)

			command = " ".join([
				binary,
				# Output
				"-d", output_dir,
				# Input traffic
				"configs/example/garnet_synth_traffic.py",
				flags
			])

			os.system(command)

			packet_latency = subprocess.check_output("grep -nri average_flit_latency  {0:s}  | sed 's/.*system.ruby.network.average_flit_latency\s*//'".format(output_dir), shell=True)
			result.add_packet_latency(injection_rate, packet_latency)

			injection_rate+=0.02

# Print all results.
for result in results:
	print(" ".join([
		"cores: %d" 	% result.network_config.num_cores,
		"benchmark: " + result.benchmark.upper(),
		"vc-%d" 			% result.network_config.virtual_channels
	]))

	for measurement in result.measurements:
		print(" ".join([
			"injection_rate: %1.2f" % measurement.injection_rate,
			"packet_latency: %f" % measurement.packet_latency,
		]))