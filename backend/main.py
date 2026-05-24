from flask import Flask, jsonify, request
from flask_cors import CORS
from simulation import Simulation 

app = Flask(__name__)
CORS(app)

sim = Simulation(grid_size=20, num_robots=20)

@app.route('/state', methods=['GET'])
def get_state(): return jsonify(sim.get_state())

@app.route('/step', methods=['POST'])
def step():
    sim.step()
    return jsonify(sim.get_state())

@app.route('/jump', methods=['POST'])
def jump():
    data = request.json
    steps = int(data.get('steps', 100))
    for _ in range(steps):
        sim.step()
    return jsonify(sim.get_state())

@app.route('/reset', methods=['POST'])
def reset():
    sim.reset()
    return jsonify(sim.get_state())

if __name__ == '__main__':
    print("Server starting on Port 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True)