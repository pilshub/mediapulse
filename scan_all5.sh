#!/bin/bash
URL="https://mediapulse.up.railway.app"
CK="cookie2.txt"

curl -s -c $CK -X POST "$URL/login" -d "password=mediapulse2000" -L > /dev/null 2>&1

PLAYERS=(
  '{"name":"Rodri Sanchez","twitter":"rodrisanchez_10","instagram":"rodrisanchez_10","club":"Al-Arabi SC","transfermarkt_id":"630995"}'
  '{"name":"Curro Sanchez","twitter":"CurroSanchez16","instagram":"currosanchez16","club":"Burgos CF","transfermarkt_id":"208116"}'
  '{"name":"Jose Matos","instagram":"jmatosgarcia","club":"AD Ceuta FC","transfermarkt_id":"268957"}'
  '{"name":"Jose Campana","twitter":"JoseGCampana","instagram":"josegomezcampana24","club":"AD Ceuta FC","transfermarkt_id":"120095"}'
  '{"name":"Antonio Casas","twitter":"antoniocasas_9","instagram":"a_casas20","club":"Venezia FC","transfermarkt_id":"537767"}'
)

for i in "${!PLAYERS[@]}"; do
  P="${PLAYERS[$i]}"
  NAME=$(echo $P | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null || echo "Player $i")
  
  echo "===== [$(date +%H:%M:%S)] ESCANEANDO $((i+1))/5: $NAME ====="
  
  RESP=$(curl -s -b $CK -X POST "$URL/api/scan" -H "Content-Type: application/json" -d "$P")
  echo "Respuesta: $RESP"
  
  # Poll until done
  TRIES=0
  while [ $TRIES -lt 120 ]; do
    sleep 10
    TRIES=$((TRIES+1))
    STATUS=$(curl -s -b $CK "$URL/api/scan/status" 2>/dev/null)
    RUNNING=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('running',False))" 2>/dev/null)
    PROG=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('progress',''))" 2>/dev/null)
    
    if [ "$RUNNING" = "False" ] || [ "$RUNNING" = "false" ]; then
      echo "[$(date +%H:%M:%S)] $NAME COMPLETADO"
      break
    fi
    echo "[$(date +%H:%M:%S)] $NAME - $PROG"
  done
  
  sleep 5
done

echo "===== [$(date +%H:%M:%S)] TODOS LOS ESCANEOS COMPLETADOS ====="
