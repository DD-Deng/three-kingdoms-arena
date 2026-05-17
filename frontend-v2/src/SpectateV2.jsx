import { useSearchParams } from 'react-router-dom'

export default function SpectateV2() {
  const [params] = useSearchParams()
  const gameId = params.get('game')

  return (
    <div className="page">
      <h1>Hello from Spectate v2</h1>
      <p>观战页面正在建设中。</p>
      {gameId && <p>Game ID: {gameId}</p>}
    </div>
  )
}
