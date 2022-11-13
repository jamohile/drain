import os
import subprocess

# import pdb; pdb.set_trace()
# first compile then run
binary = 'build/Garnet_standalone/gem5.opt'
# os.system("scons -j15 {}".format(binary))


bench_caps=[ "BIT_ROTATION", "SHUFFLE", "TRANSPOSE" ]
bench=[ "bit_rotation", "shuffle", "transpose" ]
routing_algorithm=["ADAPT_RAND_", "UP_DN_", "Escape_VC_UP_DN_"]

# A single network topology configuration.
class NetworkConfiguration:
	def __init__(self, num_cores, num_rows, mesh_config, spin_config):
		self.num_cores = num_cores
		self.num_rows = num_rows
		self.mesh_config = mesh_config
		self.spin_config = spin_config

network_configurations = [
	NetworkConfiguration(
		num_cores=64,
		num_rows=8,
		mesh_config="64_nodes-connectivity_matrix_0-links_removed_0.txt",
		spin_config="spin_configs/SR_64_nodes-connectivity_matrix_0-links_removed_0.txt"
	),

	NetworkConfiguration(
		num_cores=256,
    num_rows=16,
		mesh_config="256_nodes-connectivity_matrix_0-links_removed_0.txt",
		spin_config="spin_configs/256_nodes-connectivity_matrix_0-links_removed_0.txt"
	)
]

os.system('rm -rf ./results')
os.system('mkdir results')

out_dir = './results'
cycles = 100000
vnet = 0
tr = 1
vc_ = 4
rout_ = 0
spin_freq = 1024

for network_config in network_configurations:
	for b in range(len(bench)):
		print ("cores: {2:d} b: {0:s} vc-{1:d}".format(bench_caps[b], vc_, network_config.num_cores))
		pkt_lat = 0
		injection_rate = 0.02

		while(pkt_lat < 200.00):
			# Allow pretty-print of injection rate with desired precision.
			formatted_injection_rate = "{0:1.2f}".format(injection_rate)

			# Location to output the result of this specific run.
			output_dir = "/".join([
				out_dir,
				str(network_config.num_cores),
				routing_algorithm[rout_],
				bench_caps[b],
				"freq-" + str(spin_freq),
				"vc-" + str(vc_),
				"inj-" + str(injection_rate)
			])

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
				"--spin-freq=" + str(spin_freq),
				"--vcs-per-vnet=" + str(vc_),
				"--injectionrate=" + formatted_injection_rate,
				"--synthetic=" + bench[b],
				"--routing-algorithm=" + str(rout_)
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
			print ("output_dir: %s" %(output_dir))

			packet_latency = subprocess.check_output("grep -nri average_flit_latency  {0:s}  | sed 's/.*system.ruby.network.average_flit_latency\s*//'".format(output_dir), shell=True)

			# print packet_latency
			pkt_lat = float(packet_latency)
			print ("injection_rate={0:s} \t Packet Latency: {1:f} ".format(formatted_injection_rate, pkt_lat))
			injection_rate+=0.02


############### Extract results here ###############
for network_config in network_configurations:
	for b in range(len(bench)):
		print ("cores: {} benchmark: {} vc-{}".format(network_config.num_cores, bench_caps[b], vc_))
		pkt_lat = 0
		injection_rate = 0.02
		while (pkt_lat < 200.00):
			output_dir= ("{0:s}/{1:d}/{3:s}/{2:s}/freq-{6:d}/vc-{4:d}/inj-{5:1.2f}".format(out_dir, network_config.num_cores,  bench_caps[b], routing_algorithm[rout_], vc_, injection_rate, spin_freq))

			if(os.path.exists(output_dir)):
				packet_latency = subprocess.check_output("grep -nri average_flit_latency  {0:s}  | sed 's/.*system.ruby.network.average_flit_latency\s*//'".format(output_dir), shell=True)
				pkt_lat = float(packet_latency)
				print ("injection_rate={1:1.2f} \t Packet Latency: {0:f} ".format(pkt_lat, injection_rate))
				injection_rate+=0.02

			else:
				pkt_lat = 1000