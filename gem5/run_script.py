from cmath import exp
from logging import root
import os
from re import M
from struct import pack
import subprocess
import json
import multiprocessing
import signal
import time

BINARY = 'build/Garnet_standalone/gem5.opt'
SIMULATOR = 'configs/example/garnet_synth_traffic.py'
OUTPUT = "./result"

LOGS = os.path.join(OUTPUT, "log.log")
RESULTS = os.path.join(OUTPUT, "results")
JSON = os.path.join(OUTPUT, "output.json")

log_lock = multiprocessing.Lock()

def log(text):
	log_lock.acquire()

	with open(LOGS, 'a') as f:
		f.write(text + '\n')

	log_lock.release()


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

class SoftwareConfiguration:
	"""
	A single instance of software that will be tested against the network.
	"""
	def __init__(self, benchmark, cycles):
		self.benchmark = benchmark
		self.cycles = cycles

class SimulationConfiguration:
	"""
	Defines the meta-level configuration of this simulation.
	"""
	def __init__(self, output_dir, max_packet_latency, injection_rate_delta, max_speculation):
		self.output_dir = output_dir
		self.max_packet_latency = max_packet_latency
		self.injection_rate_delta = injection_rate_delta
		self.max_speculation = max_speculation


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

	def __init__(self, network_config, software_config, simulation_config):
		self.network_config = network_config
		self.software_config = software_config
		self.simulation_config = simulation_config

	def get_flags(self, injection_rate):
		return [
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
			"--synthetic=" 						+ self.software_config.benchmark,
			"--sim-cycles=%d" 				% self.software_config.cycles,

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
			"--injectionrate=%1.5f"		% injection_rate,
			"--precision=6"
		]
		
	def get_output_dir(self, injection_rate):
		return os.path.join(
			self.simulation_config.output_dir,
			"%s" % self.network_config.num_cores,
			self.network_config.routing_algorithm.name,
			self.software_config.benchmark.upper(),
			"freq-%d" 			% self.network_config.spin_freq,
			"vc-%d" 				% self.network_config.virtual_channels,
			"inj-%1.5f" 		% injection_rate
		)
	
	def run(self):
		log("Starting experiment: %s" % self.name())

		# Make sure that this experiment can create more subprocesses.
		curr_proc = multiprocessing.current_process()
		curr_proc.daemon = False

		manager = multiprocessing.Manager()

		# We don't know how many injection rates will be tried out.
		# So, whenever a worker becomes available, it will try out a new rate.
		# When the one finds that the experiment is complete, it will signal that to everyone.
		last_injection_rate = 0
		done = manager.Event()

		# Since we do not know how many injection rates should be tried, any parallelism here is speculative.
		# The penalty is that by running multiple at once, we may slow down others.
		# So, we balance how far we speculate by limiting the number of workers.
		workers = manager.Semaphore(self.simulation_config.max_speculation)
		# Once a worker discovers we are done, we need to cancel any uncompleted speculation.
		# To do this, we add all workers to a list as they are created, and pass their index to the workers themselves.
		# In the dictionary, we map these indices to the actual worker process.
		# When a worker completes, we simply unmap them from the dictionary.
		# Then, at the end, any still-mapped workers can be terminated.
		workers_list = []
		workers_dict = manager.dict()

		# Whenever the datastructures above are mutated, they must be access controlled.
		# Exceptions are already thread-safe structures.
		lock = manager.Lock()

		# Completed results from each worker.
		measurements_queue = manager.Queue()

		def worker(injection_rate):
			def worker_log(message):
				self.log("worker %1.5f -> %s" % (injection_rate, message))

			output_dir = self.get_output_dir(injection_rate)
			worker_log("starting")

			# Run simulator with provided configuration.
			subprocess.call([BINARY, "-d", output_dir, SIMULATOR] + self.get_flags(injection_rate))

			# Scan through the simulator's output, to specificially find the average flit latency.
			_, packet_latency = subprocess.check_output([
				"grep", "system.ruby.network.average_flit_latency", os.path.join(output_dir, "stats.txt"),
			]).split()
			packet_latency = float(packet_latency)
			
			measurements_queue.put(Measurement(injection_rate, packet_latency))

			worker_log("done, with latency %f" % packet_latency)
			if packet_latency > self.simulation_config.max_packet_latency:
				done.set()
				worker_log("reached latency limit")

			# TODO: this may already be threadsafe.
			lock.acquire()
			workers_dict.pop(injection_rate)
			lock.release()
			workers.release()

    # Until we are done this experiment, keep dispatching workers.
		while not done.is_set():
			workers.acquire()
			lock.acquire()

			# It's possible that in the time it took us to acquire a worker, the experiment finished.
			if done.is_set():
				workers.release()
				lock.release()
				break

			last_injection_rate += self.simulation_config.injection_rate_delta

			injection_rate = last_injection_rate

			worker_process = multiprocessing.Process(target=worker, args=[injection_rate])
			worker_index = len(workers_list)

			workers_dict[injection_rate] = worker_index
			workers_list.append(worker_process)
			
			lock.release()
			
			worker_process.start()

		# At this point, all meaningful work for this experiment is completed.
		# But, there may still be speculative processes running.
		self.log("exited")
		
		# TODO: only terminate higher rate stragglers.
		# For now, we assume that the workers complete in order.
		lock.acquire()

		num_stragglers = len(workers_dict)
		for straggler_index in workers_dict.values():
			self.log("terminating worker number %d." % straggler_index)
			# Terminating a process doesn't kill its children, so do so manually.
			os.system("pkill -P %d" % workers_list[straggler_index].pid)
			workers_list[straggler_index].terminate()

			self.log("terminated worker number %d." % straggler_index)

		lock.release()

		self.log("terminated %d stragglers." % num_stragglers)

		# Now, convert the measurements queue back into a normal list.
		measurements_queue.put(None)
		measurements = list(iter(measurements_queue.get, None))

		self.log("done. generated %d measurements." % len(measurements))
		return measurements

	def toDict(self):
		return {
			"cores": self.network_config.num_cores,
			"benchmark": self.software_config.benchmark.upper(),
			"vc": self.network_config.virtual_channels,
		}
	
	def name(self):
		return "cores-%d_benchmark-%s_vc-%d" % (self.network_config.num_cores, self.software_config.benchmark.upper(), self.network_config.virtual_channels)

	def log(self, message):
		log("Experiment: %s -> %s" % (self.name(), message))

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

software_configurations = [
	SoftwareConfiguration(benchmark="bit_rotation", cycles=1e5),
	SoftwareConfiguration(benchmark="shuffle", cycles=1e5),
	SoftwareConfiguration(benchmark="transpose", cycles=1e5)
]

def run_experiment(experiment):
	return experiment.run()

def main():
	# Build simulator.
	# os.system("scons -j15 {}".format(BINARY))

	# Clean up any leftover outputs.
	subprocess.call("rm -rf %s" % OUTPUT, shell=True)

	subprocess.call("mkdir %s" % OUTPUT, shell=True)
	subprocess.call('mkdir %s' % RESULTS, shell=True)

	simulation_config = SimulationConfiguration(output_dir=RESULTS, max_packet_latency=200.0, injection_rate_delta=0.001, max_speculation=5)

	# Prepare experiments.
	experiments = []
	for network_config in network_configurations:
		for software_config in software_configurations:
			experiments.append(Experiment(network_config, software_config, simulation_config))
	
	# Run all experiments using multithreading.
	# Note: this assumes that experiments do not try to write to the same location, or otherwise break independence.
	log("Starting experiments.")
	start_time = time.time()

	pool = multiprocessing.Pool()
	results = pool.map(run_experiment, experiments)

	log("Done all experiments after %s seconds." % (time.time() - start_time))

	# Print all results.
	results_dict = []
	for experiment, measurements in zip(experiments, results):
		results_dict.append({
			"experiment": experiment.toDict(),
			"results": [m.toDict() for m in measurements]
		})
	output = json.dumps(results_dict, indent=2)

	log(output)
	with open(JSON, "w") as f:
		f.write(output)
main()
