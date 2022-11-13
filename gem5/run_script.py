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

out_dir = './results'
cycles = 100000

os.system('rm -rf ./results')
os.system('mkdir results')

def get_output_dir(network_config, benchmark, injection_rate):
	path = [
		out_dir,
		str(network_config.num_cores),
		network_config.routing_algorithm.name,
		benchmark.upper(),
		"freq-" + str(network_config.spin_freq),
		"vc-" + str(network_config.virtual_channels),
		"inj-" + str(injection_rate)
	]

	return "/".join(path)

for network_config in network_configurations:
	for benchmark in benchmarks:
		print ("cores: {2:d} b: {0:s} vc-{1:d}".format(benchmark.upper(), network_config.virtual_channels, network_config.num_cores))
		pkt_lat = 0
		injection_rate = 0.02

		while(pkt_lat < 200.00):
			# Allow pretty-print of injection rate with desired precision.
			formatted_injection_rate = "{0:1.2f}".format(injection_rate)

			output_dir = get_output_dir(network_config, benchmark, injection_rate)

			# Control flags for Gem5.
			flags = " ".join([
				"--topology=irregularMesh_XY",
				"--network=garnet2.0",
				"--router-latency=1",
				"--spin=1",
				"--spin-mult=1",
				"--uTurn-crossbar=1",
				"--inj-vnet=0",
				"--num-cpus=" + str(network_config.num_cores),
				"--num-dirs=" + str(network_config.num_cores),
				"--mesh-rows=" + str(network_config.num_rows),
				"--sim-cycles=" + str(cycles),
				"--conf-file=" + network_config.mesh_config,
				"--spin-file=" + network_config.spin_config,
				"--spin-freq=" + str(network_config.spin_freq),
				"--vcs-per-vnet=" + str(network_config.virtual_channels),
				"--injectionrate=" + formatted_injection_rate,
				"--synthetic=" + benchmark,
				"--routing-algorithm=" + str(network_config.routing_algorithm.key),
			])

			############ gem5 command-line ###########
			command = " ".join([
				binary,
				# Output
				"-d", output_dir,
				# Input traffic
				"configs/example/garnet_synth_traffic.py",
				flags
			])

			os.system(command)

			############ gem5 output-directory ##############
			print ("output_dir: %s" % (output_dir))

			packet_latency = subprocess.check_output("grep -nri average_flit_latency  {0:s}  | sed 's/.*system.ruby.network.average_flit_latency\s*//'".format(output_dir), shell=True)

			# print packet_latency
			pkt_lat = float(packet_latency)
			print ("injection_rate={0:s} \t Packet Latency: {1:f} ".format(formatted_injection_rate, pkt_lat))
			injection_rate+=0.02


############### Extract results here ###############
for network_config in network_configurations:
	for benchmark in benchmarks:
		print ("cores: {} benchmark: {} vc-{}".format(network_config.num_cores, benchmark.upper(), network_config.virtual_channels))
		pkt_lat = 0
		injection_rate = 0.02
		while (pkt_lat < 200.00):
			output_dir = get_output_dir(network_config, benchmark, injection_rate)

			if(os.path.exists(output_dir)):
				packet_latency = subprocess.check_output("grep -nri average_flit_latency  {0:s}  | sed 's/.*system.ruby.network.average_flit_latency\s*//'".format(output_dir), shell=True)
				pkt_lat = float(packet_latency)
				print ("injection_rate={1:1.2f} \t Packet Latency: {0:f} ".format(pkt_lat, injection_rate))
				injection_rate+=0.02

			else:
				pkt_lat = 1000