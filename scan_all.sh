#!/bin/bash
COOKIE="cookie.txt"
URL="https://mediapulse.up.railway.app"

# Login
curl -s -c $COOKIE -X POST "$URL/login" -d "password=mediapulse2000" -L > /dev/null 2>&1

# Players to scan (id, name, twitter, instagram, club, tm_id)
declare -a PLAYERS=(
  '{"name":"Rodri Sanchez","twitter":"rodrisanchez_10","instagram":"rodrisanchez_10","club":"Al-Arabi SC","transfermarkt_id":"630995"}'
  '{"name":"Curro Sanchez","twitter":"CurroSanchez16","instagram":"currosanchez16","club":"Burgos CF","transfermarkt_id":"208116"}'
  '{"name":"Jose Matos","instagram":"jmatosgarcia","club":"AD Ceuta FC","transfermarkt_id":"268957"}'
  '{"name":"Jose Campana","twitter":"JoseGCampana","instagram":"josegomezcampana24","club":"AD Ceuta FC","transfermarkt_id":"120095"}'
  '{"name":"Antonio Casas","twitter":"antoniocasas_9","instagram":"a_casas20","club":"Venezia FC","transfermarkt_id":"537767"}'
)

# Wait for any running scan to finish
echo "[$(date +%H:%M:%S)] Esperando a que termine el escaneo en curso..."
while true; do
  STATUS=$(curl -s -b $COOKIE "$URL/api/scan/status")
  RUNNING=$(echo $STATUS | grep -o '"running":true')
  if [ -z "$RUNNING" ]; then
    echo "[$(date +%H:%M:%S)] Escaneo anterior terminado."
    break
  fi
  PROGRESS=$(echo $STATUS | grep -o '"progress":"[^"]*"' | cut -d'"' -f4)
  echo "[$(date +%H:%M:%S)] En curso: $PROGRESS"
  sleep 10
done

# Check which players already have data
for i in "${!PLAYERS[@]}"; do
  PLAYER="${PLAYERS[$i]}"
  NAME=$(echo $PLAYER | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
  
  # Get player ID
  PID=$(curl -s -b $COOKIE "$URL/api/players" | grep -o "\"id\":[0-9]*,\"name\":\"$NAME\"" | grep -o '[0-9]*' | head -1)
  
  if [ -n "$PID" ]; then
    SUMMARY=$(curl -s -b $COOKIE "$URL/api/summary?player_id=$PID")
    PRESS=$(echo $SUMMARY | grep -o '"press_count":[0-9]*' | grep -o '[0-9]*')
    MENTIONS=$(echo $SUMMARY | grep -o '"mentions_count":[0-9]*' | grep -o '[0-9]*')
    
    if [ "$PRESS" -gt 0 ] 2>/dev/null || [ "$MENTIONS" -gt 0 ] 2>/dev/null; then
      echo "[$(date +%H:%M:%S)] SKIP $NAME - ya tiene datos (prensa:$PRESS menciones:$MENTIONS)"
      continue
    fi
  fi
  
  echo "[$(date +%H:%M:%S)] ESCANEANDO: $NAME"
  RESP=$(curl -s -b $COOKIE -X POST "$URL/api/scan" -H "Content-Type: application/json" -d "$PLAYER")
  echo "[$(date +%H:%M:%S)] Respuesta: $RESP"
  
  # Wait for scan to finish
  while true; do
    sleep 15
    STATUS=$(curl -s -b $COOKIE "$URL/api/scan/status")
    RUNNING=$(echo $STATUS | grep -o '"running":true')
    if [ -z "$RUNNING" ]; then
      echo "[$(date +%H:%M:%S)] $NAME - Escaneo completado!"
      break
    fi
    PROGRESS=$(echo $STATUS | grep -o '"progress":"[^"]*"' | cut -d'"' -f4)
    echo "[$(date +%H:%M:%S)] $NAME - $PROGRESS"
  done
  
  sleep 5
done

echo "[$(date +%H:%M:%S)] TODOS LOS ESCANEOS COMPLETADOS"
