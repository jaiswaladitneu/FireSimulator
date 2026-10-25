import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [status, setStatus] = useState('Ready')
  const [tick, setTick] = useState(0)
  const [scenarioCreated, setScenarioCreated] = useState(false)
  const [scenarioName, setScenarioName] = useState('Wildfire Demo')
  const [gridWidth, setGridWidth] = useState(50)
  const [gridHeight, setGridHeight] = useState(50)
  const [windSpeed, setWindSpeed] = useState(12)
  const [windDirection, setWindDirection] = useState(45)
  const [simulationSpeed, setSimulationSpeed] = useState(1)
  const [burningCells, setBurningCells] = useState(0)
  const [burnedCells, setBurnedCells] = useState(0)
  const [suppressedCells, setSuppressedCells] = useState(0)
  const [grid, setGrid] = useState<number[][]>([])

  const updateSimulationState = async () => {
  try {
    const response = await fetch(
      'http://127.0.0.1:8000/simulation/state'
    )

    if (!response.ok) {
      throw new Error('Failed to get simulation state')
    }

    const data = await response.json()

    setStatus(data.state)
    setTick(data.tick)

    setBurningCells(data.counts.burning)
    setBurnedCells(data.counts.burned)
    setSuppressedCells(data.counts.suppressed)

    setGrid(data.grid)

    console.log('Simulation state:', data)
  } catch (error) {
    console.error('Error getting simulation state:', error)
  }
}

  const createScenario = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/scenarios', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: scenarioName,
        width: gridWidth,
        height: gridHeight,
        seed: 0,
        wind_direction: windDirection,
        wind_speed: windSpeed,
        ignition_points: [{
            x: Math.floor(gridWidth / 2),
            y: Math.floor(gridHeight / 2),
            tick: 0,
          },],
      }),
    })

    if (!response.ok) {
      throw new Error('Failed to create scenario')
    }

    const data = await response.json()

    setScenarioCreated(true)
    setStatus('Ready')

    await updateSimulationState()

    console.log('Scenario created:', data)
  } catch (error) {
    console.error('Error creating scenario:', error)
  }
}

  const playSimulation = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/simulation/play', {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error('Failed to start simulation')
    }

    const data = await response.json()

    setStatus(data.state)
    setTick(data.tick)
    setBurningCells(data.counts.burning)
    setBurnedCells(data.counts.burned)
    setSuppressedCells(data.counts.suppressed)
    setGrid(data.grid)

    console.log('Simulation started:', data)
      } catch (error) {
        console.error('Error starting simulation:', error)
      }
}

  const pauseSimulation = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/simulation/pause', {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error('Failed to pause simulation')
    }

    const data = await response.json()

    setStatus(data.state)
    setTick(data.tick)
    setBurningCells(data.counts.burning)
    setBurnedCells(data.counts.burned)
    setSuppressedCells(data.counts.suppressed)
    setGrid(data.grid)

    console.log('Simulation paused:', data)
  } catch (error) {
    console.error('Error pausing simulation:', error)
  }
}

    const changeSimulationSpeed = async (speed: number) => {
    try {
      const response = await fetch(
        'http://127.0.0.1:8000/simulation/speed',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            speed: speed,
          }),
        }
      )

      if (!response.ok) {
        throw new Error('Failed to change simulation speed')
      }

      const data = await response.json()

      setSimulationSpeed(data.speed)

      console.log('Simulation speed changed:', data)
    } catch (error) {
      console.error('Error changing simulation speed:', error)
    }
  }

  const stepSimulation = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/simulation/step', {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error('Failed to step simulation')
    }

    const data = await response.json()

    setTick(data.tick)
    setStatus(data.state)
    setBurningCells(data.counts.burning)
    setBurnedCells(data.counts.burned)
    setSuppressedCells(data.counts.suppressed)
    setGrid(data.grid)

    console.log('Simulation stepped:', data)
  } catch (error) {
    console.error('Error stepping simulation:', error)
  }
}

  const resetSimulation = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/simulation/reset', {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error('Failed to reset simulation')
    }

    const data = await response.json()

    setTick(data.tick)
    setStatus(data.state)
    setBurningCells(data.counts.burning)
    setBurnedCells(data.counts.burned)
    setSuppressedCells(data.counts.suppressed)
    setGrid(data.grid)

    console.log('Simulation reset:', data)
  } catch (error) {
    console.error('Error resetting simulation:', error)
  }
}

      useEffect(() => {
      if (status !== 'running') {
        return
      }

      const interval = setInterval(async () => {
        try {
          const response = await fetch(
            'http://127.0.0.1:8000/simulation/tick',
            {
              method: 'POST',
            }
          )

          if (!response.ok) {
            throw new Error('Failed to advance simulation')
          }

          const data = await response.json()

          setStatus(data.state)
          setTick(data.tick)
          setBurningCells(data.counts.burning)
          setBurnedCells(data.counts.burned)
          setSuppressedCells(data.counts.suppressed)
          setGrid(data.grid)

        } catch (error) {
          console.error('Error advancing simulation:', error)
        }
      }, 1000)

      return () => clearInterval(interval)
    }, [status, simulationSpeed])

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>🔥 FireSimulator</h1>
          <p>Wildfire Simulation & Control Dashboard</p>
        </div>

        <div className="system-status">
          <span className="status-dot"></span>
          System Online
        </div>
      </header>

      <main className="dashboard">
        <section className="panel scenario-panel">
          <h2>Scenario Configuration</h2>

          <label>Scenario Name</label>
          <input
            type="text"
            value={scenarioName}
            onChange={(e) => setScenarioName(e.target.value)}
          />

          <div className="input-row">
            <div>
              <label>Grid Width</label>
              <input
                type="number"
                value={gridWidth}
                onChange={(e) => setGridWidth(Number(e.target.value))}
              />
            </div>

            <div>
              <label>Grid Height</label>
              <input
                type="number"
                value={gridHeight}
                onChange={(e) => setGridHeight(Number(e.target.value))}
              />
            </div>
          </div>

          <label>Wind Speed</label>
          <input
              type="number"
              value={windSpeed}
              onChange={(e) => setWindSpeed(Number(e.target.value))}
          />

          <label>Wind Direction</label>
          <select
            value={windDirection}
            onChange={(e) => setWindDirection(Number(e.target.value))}
          >
            <option value={0}>North</option>
            <option value={45}>North-East</option>
            <option value={90}>East</option>
            <option value={135}>South-East</option>
            <option value={180}>South</option>
            <option value={225}>South-West</option>
            <option value={270}>West</option>
            <option value={315}>North-West</option>
          </select>

          <button className="create-button" onClick={createScenario}>
          {scenarioCreated ? '✓ Scenario Created' : 'Create Scenario'}
          </button>
        </section>

        <section className="panel simulation-panel">
          <div className="simulation-header">
            <div>
              <h2>Live Fire Simulation</h2>
              <p>Current wildfire state</p>
            </div>

            <span className={`simulation-status ${status.toLowerCase()}`}>
              {status}
            </span>
          </div>

          <div
            className="map-grid"
            style={{
              gridTemplateColumns: `repeat(${gridWidth}, 1fr)`,
            }}
            >
            {grid.flat().map((cellState, index) => {
              let cellClass = 'forest'

              if (cellState === 1) {
                cellClass = 'burning'
              } else if (cellState === 2) {
                cellClass = 'fire'
              } else if (cellState === 3) {
                cellClass = 'burned'
              } else if (cellState === 4) {
                cellClass = 'suppressed'
              }

              return (
                <div
                  key={index}
                  className={`map-cell ${cellClass}`}
                ></div>
              )
            })}
          </div>

          <div className="controls">
            <button onClick={playSimulation}>▶ Play</button>
            <button onClick={pauseSimulation}>⏸ Pause</button>
            <button onClick={stepSimulation}>⏭ Step</button>
            <button onClick={resetSimulation}>↻ Reset</button>
          </div>

          <div className="speed-control">
            <label>Simulation Speed</label>

            <select
              value={simulationSpeed}
              onChange={(e) => changeSimulationSpeed(Number(e.target.value))}
            >
              <option value={0.5}>0.5×</option>
              <option value={1}>1×</option>
              <option value={2}>2×</option>
              <option value={4}>4×</option>
            </select>
          </div>

        </section>

        <section className="panel stats-panel">
          <h2>Simulation Statistics</h2>

          <div className="stat">
            <span>Status</span>
            <strong>{status}</strong>
          </div>

          <div className="stat">
            <span>Current Tick</span>
            <strong>{tick}</strong>
          </div>

          <div className="stat">
            <span>Grid Size</span>
            <strong>{gridWidth} × {gridHeight}</strong>
          </div>

          <div className="stat">
            <span>Burning Cells</span>
            <strong>{burningCells}</strong>
          </div>

          <div className="stat">
            <span>Burned Cells</span>
            <strong>{burnedCells}</strong>
          </div>

          <div className="stat">
            <span>Suppressed Cells</span>
            <strong>{suppressedCells}</strong>
          </div>

          <div className="legend">
            <h3>Map Legend</h3>

            <div><span className="legend-box forest"></span> Unburned</div>
            <div><span className="legend-box burning"></span> Burning</div>
            <div><span className="legend-box fire"></span> Active Fire</div>
            <div><span className="legend-box burned"></span> Burned</div>
          </div>

          <div className="legend">
            <h3>Map Legend</h3>

            <div>
              <span className="legend-box forest"></span> Unburned
            </div>

            <div>
              <span className="legend-box burning"></span> Burning
            </div>

            <div>
              <span className="legend-box fire"></span> Active Fire
            </div>

            <div>
              <span className="legend-box burned"></span> Burned
            </div>

            <div>
              <span className="legend-box suppressed"></span> Suppressed
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App