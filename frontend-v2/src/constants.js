export const FACTIONS = ['蜀', '魏', '吴']

export const FACTION_COLORS = {
  蜀: '#c4453a',
  魏: '#3a6dc4',
  吴: '#3a9a4a',
}

export const FACTION_MONARCHS = {
  蜀: '刘备',
  魏: '曹操',
  吴: '孙权',
}

export const CITY_POSITIONS = {
  洛阳: { x: 170, y: 20 },
  长安: { x: 40, y: 85 },
  邺城: { x: 260, y: 25 },
  宛城: { x: 150, y: 110 },
  襄阳: { x: 245, y: 170 },
  成都: { x: 40, y: 210 },
  建业: { x: 260, y: 215 },
}

export const ADJACENCY = [
  ['洛阳', '长安'], ['洛阳', '宛城'], ['洛阳', '邺城'],
  ['长安', '宛城'], ['长安', '成都'],
  ['邺城', '宛城'],
  ['宛城', '襄阳'],
  ['襄阳', '成都'], ['襄阳', '建业'],
]
