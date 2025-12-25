#include <Servo.h>
Servo gripper;

// ================= PIN MAP =================
#define X_ENA   4
#define X_DIR   3
#define X_PUL   2
#define X_LIMIT 22

#define Y_ENA   10
#define Y_DIR   9
#define Y_PUL   8
#define Y_LIMIT 24

#define Z_ENA   5
#define Z_DIR   6
#define Z_PUL   7
#define Z_LIMIT 26

// ================= SERVO =================
#define SERVO_PIN   44
#define SERVO_OPEN  30
#define SERVO_CLOSE 110

// ================= MECH =================
#define X_STEPS_PER_MM 66.0f
#define Y_STEPS_PER_MM 25.0f

// ================= OFFSET BASE (OPTIONAL) =================
#define DENTA_X 10
#define DENTA_Y 20

// ================= Z =================
#define Z_PICK_STEPS 6700
#define BIN_Z_STEPS  6700

#define Z_UP_START_US   1600
#define Z_UP_RUN_US     100
#define Z_UP_ACC_US     4

#define Z_DOWN_START_US 1000
#define Z_DOWN_RUN_US    95
#define Z_DOWN_ACC_US    8

// ================= BIN =================
#define BIN_X 0.0f
#define BIN_Y 30.0f

// ================= TIMING =================
#define STEP_HIGH_US 5

#define HOME_X_US     100
#define HOME_Y_US     150
#define HOME_Z_US     200

#define ARRIVE_SETTLE_MS 1100
#define DEC_TIMEOUT_MS   10000  // mode1 only

// ================= DIR / LIMIT =================
#define X_DIR_HOME LOW
#define X_DIR_FWD  HIGH
#define Y_DIR_HOME LOW
#define Y_DIR_FWD  HIGH
#define Z_DIR_HOME HIGH
#define Z_DIR_FWD  LOW
#define LIMIT_HIT  LOW

// ============================================================
// ============= SCAN MOVE (GIỮ NGUYÊN QUINTIC) ================
// ============================================================
#define SCAN_X_VMAX_MM_S       250.0f
#define SCAN_Y_VMAX_MM_S       500.0f
#define SCAN_MIN_MOVE_TIME_S      0.3f
#define SCAN_X_MIN_STEP_US  10U
#define SCAN_Y_MIN_STEP_US  1U

// ============================================================
// =================== RAPID MOVE =============================
// ============================================================
#define RAPID_CTRL_US       800UL   // 2ms / tick
#define RAPID_MIN_TIME_S    0.25f
#define RAPID_VX_MM_S       3000.0f
#define RAPID_VY_MM_S       1300.0f

// ============================================================
// ================= POINT TABLE ==============================
// ============================================================
const float PX_BASE[9] = {
  120 + DENTA_X, 240 + DENTA_X, 360 + DENTA_X,
  360 + DENTA_X, 240 + DENTA_X, 120 + DENTA_X,
  120 + DENTA_X, 240 + DENTA_X, 360 + DENTA_X
};

const float PY_BASE[9] = {
  0 + DENTA_Y,   0 + DENTA_Y,   0 + DENTA_Y,
  400 + DENTA_Y, 400 + DENTA_Y, 400 + DENTA_Y,
  800 + DENTA_Y, 800 + DENTA_Y, 800 + DENTA_Y
};

// ================= RUNTIME =================
float curX = 0, curY = 0;
float deltaX = 0, deltaY = 0;
inline float PX(uint8_t i){ return PX_BASE[i-1] + deltaX; }
inline float PY(uint8_t i){ return PY_BASE[i-1] + deltaY; }

// ================= STATE =================
volatile bool stopReq = false;
bool homed = false;
int mode = 1; // 1/2/3

// MODE2: pick list
uint8_t pickList[9];
uint8_t pickCount = 0;
uint8_t pickIdx   = 0;

// ================= LOW LEVEL =================
inline void pulse(int pin){
  digitalWrite(pin, HIGH);
  delayMicroseconds(STEP_HIGH_US);
  digitalWrite(pin, LOW);
}
inline bool hitX(){ return digitalRead(X_LIMIT)==LIMIT_HIT; }
inline bool hitY(){ return digitalRead(Y_LIMIT)==LIMIT_HIT; }
inline bool hitZ(){ return digitalRead(Z_LIMIT)==LIMIT_HIT; }

// Quintic smoothstep
static inline float sQuintic(float u){
  if(u<=0) return 0;
  if(u>=1) return 1;
  return u*u*u*(10 + u*(-15 + 6*u));
}

// ============================================================
// ================= MOVE XY: SCAN (QUINTIC) ===================
// ============================================================
void moveXY_scan(float x1, float y1){
  if(stopReq) return;

  float x0 = curX, y0 = curY;
  float dx_mm = x1 - x0;
  float dy_mm = y1 - y0;
  if(dx_mm==0 && dy_mm==0) return;

  long dxStepsSigned = lroundf(dx_mm * X_STEPS_PER_MM);
  long dyStepsSigned = lroundf(dy_mm * Y_STEPS_PER_MM);

  long dxSteps = labs(dxStepsSigned);
  long dySteps = labs(dyStepsSigned);
  long m = max(dxSteps, dySteps);
  if(m <= 0){ curX=x1; curY=y1; return; }

  digitalWrite(X_DIR, (dxStepsSigned >= 0) ? X_DIR_FWD : X_DIR_HOME);
  digitalWrite(Y_DIR, (dyStepsSigned >= 0) ? Y_DIR_FWD : Y_DIR_HOME);

  float Tx = (fabsf(dx_mm) < 1e-6f) ? 0.0f : (0.35f * fabsf(dx_mm) / SCAN_X_VMAX_MM_S);
  float Ty = (fabsf(dy_mm) < 1e-6f) ? 0.0f : (0.30f * fabsf(dy_mm) / SCAN_Y_VMAX_MM_S);
  float T  = max(max(Tx, Ty), SCAN_MIN_MOVE_TIME_S);

  float delay_f = (T * 1000000.0f) / (float)m;
  uint32_t us = (uint32_t)max(1.0f, delay_f);

  uint32_t clampMin = 1;
  if(dxSteps > 0) clampMin = max(clampMin, (uint32_t)SCAN_X_MIN_STEP_US);
  if(dySteps > 0) clampMin = max(clampMin, (uint32_t)SCAN_Y_MIN_STEP_US);
  if(us < clampMin) us = clampMin;

  long xDone = 0, yDone = 0;

  for(long i=1; i<=m; i++){
    if(stopReq) return;

    float u = (float)i / (float)m;
    float s = sQuintic(u);

    long xTarget = lroundf(s * (float)dxSteps);
    long yTarget = lroundf(s * (float)dySteps);

    while(xDone < xTarget){ pulse(X_PUL); xDone++; }
    while(yDone < yTarget){ pulse(Y_PUL); yDone++; }

    delayMicroseconds(us);
  }

  while(xDone < dxSteps){ pulse(X_PUL); xDone++; delayMicroseconds(us); }
  while(yDone < dySteps){ pulse(Y_PUL); yDone++; delayMicroseconds(us); }

  curX = x1; curY = y1;
}

// ============================================================
// ================= MOVE XY: RAPID (NO ACCEL) =================
// ============================================================
void moveXY_rapid(float x1, float y1){
  if(stopReq) return;

  float x0 = curX, y0 = curY;
  float dx = x1 - x0;
  float dy = y1 - y0;

  long sxTotal = labs(lroundf(dx * X_STEPS_PER_MM));
  long syTotal = labs(lroundf(dy * Y_STEPS_PER_MM));
  if(sxTotal==0 && syTotal==0){
    curX=x1; curY=y1; return;
  }

  // set dir once
  digitalWrite(X_DIR, dx>=0 ? X_DIR_FWD : X_DIR_HOME);
  digitalWrite(Y_DIR, dy>=0 ? Y_DIR_FWD : Y_DIR_HOME);

  // === chọn thời gian T (theo velocity vector) ===
  float Tx = fabsf(dx) / RAPID_VX_MM_S;
  float Ty = fabsf(dy) / RAPID_VY_MM_S;
  float T  = max(max(Tx, Ty), RAPID_MIN_TIME_S);

  uint32_t N = max(1UL, (uint32_t)((T*1000000.0f)/RAPID_CTRL_US));

  long xCur = lroundf(curX * X_STEPS_PER_MM);
  long yCur = lroundf(curY * Y_STEPS_PER_MM);

  uint32_t t0 = micros();

  for(uint32_t k=1;k<=N;k++){
    if(stopReq) return;

    float u = (float)k / (float)N;
    float s = sQuintic(u);

    long xT = lroundf((x0 + dx*s) * X_STEPS_PER_MM);
    long yT = lroundf((y0 + dy*s) * Y_STEPS_PER_MM);

    long dxs = xT - xCur;
    long dys = yT - yCur;

    if(dxs!=0) digitalWrite(X_DIR, dxs>0?X_DIR_FWD:X_DIR_HOME);
    if(dys!=0) digitalWrite(Y_DIR, dys>0?Y_DIR_FWD:Y_DIR_HOME);

    long ax = labs(dxs);
    long ay = labs(dys);
    long m  = max(ax, ay);

    if(m>0){
      uint32_t slice = RAPID_CTRL_US / m;
      if(slice < 20) slice = 20;

      long accX=0, accY=0;
      for(long i=0;i<m;i++){
        accX += ax;
        if(accX>=m && ax){
          pulse(X_PUL);
          accX-=m;
          xCur += (digitalRead(X_DIR)==X_DIR_FWD)?1:-1;
        }
        accY += ay;
        if(accY>=m && ay){
          pulse(Y_PUL);
          accY-=m;
          yCur += (digitalRead(Y_DIR)==Y_DIR_FWD)?1:-1;
        }
        delayMicroseconds(slice);
      }
    }

    uint32_t nextTick = t0 + k*RAPID_CTRL_US;
    while((int32_t)(micros()-nextTick)<0){}
  }

  curX=x1; curY=y1;
}

// ================= MOVE Z =================
void moveZ_steps(long steps, bool down){
  int d, dRun, dAcc;

  if(down){
    d    = Z_DOWN_START_US;
    dRun= Z_DOWN_RUN_US;
    dAcc= Z_DOWN_ACC_US;
    digitalWrite(Z_DIR, Z_DIR_FWD);
  }else{
    d    = Z_UP_START_US;
    dRun= Z_UP_RUN_US;
    dAcc= Z_UP_ACC_US;
    digitalWrite(Z_DIR, Z_DIR_HOME);
  }

  for(long i=0;i<steps;i++){
    pulse(Z_PUL);
    if(d > dRun) d -= dAcc;
    if(d < dRun) d = dRun;
    delayMicroseconds(d);
  }
}

// ================= PICK SEQUENCE =================
void pickFromHereToBin(){
  if(stopReq) return;

  moveZ_steps(Z_PICK_STEPS,true);
  delay(80);
  gripper.write(SERVO_CLOSE);
  delay(400);
  moveZ_steps(Z_PICK_STEPS,false);

  if(stopReq) return;

  moveXY_rapid(BIN_X, BIN_Y);

  moveZ_steps(BIN_Z_STEPS,true);
  delay(80);
  gripper.write(SERVO_OPEN);
  delay(400);
  moveZ_steps(BIN_Z_STEPS,false);
}

// ================= HOME =================
void homeAll(){
  Serial.println("[HOME] Z...");
  digitalWrite(Z_DIR,Z_DIR_HOME);
  while(!hitZ()){
    if(stopReq) return;
    pulse(Z_PUL); delayMicroseconds(HOME_Z_US);
  }

  Serial.println("[HOME] X...");
  digitalWrite(X_DIR,X_DIR_HOME);
  while(!hitX()){
    if(stopReq) return;
    pulse(X_PUL); delayMicroseconds(HOME_X_US);
  }

  Serial.println("[HOME] Y...");
  digitalWrite(Y_DIR,Y_DIR_HOME);
  while(!hitY()){
    if(stopReq) return;
    pulse(Y_PUL); delayMicroseconds(HOME_Y_US);
  }

  curX = 0; curY = 0;
  homed = true;
  Serial.println("[HOME] DONE");
}

// ============================================================
// ================== NON-BLOCK SERIAL RX ======================
// ============================================================
static String rxBuf = "";
static bool   rxLineReady = false;
static String rxLine = "";

void serialPoll(){
  while(Serial.available()){
    char c = (char)Serial.read();
    if(c=='\r') continue;
    if(c=='\n'){
      rxLine = rxBuf;
      rxBuf = "";
      rxLine.trim();
      rxLineReady = (rxLine.length() > 0);
      return;
    }
    rxBuf += c;
    if(rxBuf.length() > 200) rxBuf.remove(0, rxBuf.length()-200);
  }
}

bool takeLine(String &out){
  if(!rxLineReady) return false;
  out = rxLine;
  rxLineReady = false;
  return true;
}

// ============================================================
// ================== RUN STATE MACHINE ========================
// ============================================================
enum RunModeState {
  RM_IDLE = 0,

  // mode1/mode2 scan use:
  RM_SCAN_MOVE,
  RM_SCAN_SETTLE,
  RM_SCAN_EVT_SENT,
  RM_WAIT_DECISION,   // mode1 only

  // after decision:
  RM_DO_PICK,

  // mode2 pick:
  RM_MODE2_PICK_GOTO,
  RM_MODE2_PICK_DO,
  RM_MODE2_PICK_SETTLE,

  // mode3 (unchanged behavior via commands)
  RM_MODE3_WAIT_GOTO,
  RM_MODE3_DO_PICK
};

RunModeState rm = RM_IDLE;
uint8_t curP = 1;
uint32_t tMark = 0;

// decision inbox (mode1)
enum Decision { DEC_NONE=0, DEC_PICK=1, DEC_SKIP=2 };
Decision pendingDec = DEC_NONE;

// mode3 current target
uint8_t mode3TargetP = 1;

void startRun(){
  if(!homed){
    Serial.println("[ERR] Not homed. Send H0 first.");
    return;
  }
  if(stopReq){
    Serial.println("[ERR] STOP active. Send UNSTOP first.");
    return;
  }

  pendingDec = DEC_NONE;
  curP = 1;

  if(mode == 1){
    Serial.println("[RUN] MODE 1 (live pick)");
    rm = RM_SCAN_MOVE;     // reuse scan travel states
  } else if(mode == 2){
    Serial.println("[RUN] MODE 2 SCAN (scan-only)");
    rm = RM_SCAN_MOVE;     // scan-only; no pick; will HOME+IDLE at end
  } else if(mode == 3){
    Serial.println("[RUN] MODE 3 (manual, no AI)");
    rm = RM_MODE3_WAIT_GOTO;
  } else {
    Serial.println("[ERR] MODE invalid");
    rm = RM_IDLE;
  }
}

void processDecisionTimeout(){
  if((uint32_t)(millis() - tMark) >= DEC_TIMEOUT_MS){
    pendingDec = DEC_SKIP;
    Serial.println("[AI] DEC TIMEOUT -> SKIP");
  }
}

void runStateMachine(){
  if(rm == RM_IDLE) return;
  if(stopReq) return;

  switch(rm){

    // ======================================================
    // MODE 1 + MODE 2 : SCAN PHASE
    // ======================================================
    case RM_SCAN_MOVE: {
      if(curP > 9){
        if(mode == 1){
          Serial.println("[MODE1] DONE -> HOME");
          homeAll();
        } else if(mode == 2){
          Serial.println("SCAN_DONE");
          Serial.println("[MODE2] SCAN DONE -> HOME");
          homeAll();
        }
        rm = RM_IDLE;
        break;
      }

      Serial.print("[SCAN] GOTO P"); Serial.println(curP);
      moveXY_scan(PX(curP), PY(curP));
      tMark = millis();
      rm = RM_SCAN_SETTLE;
    } break;

    case RM_SCAN_SETTLE: {
      if((uint32_t)(millis() - tMark) >= ARRIVE_SETTLE_MS){
        rm = RM_SCAN_EVT_SENT;
      }
    } break;

    case RM_SCAN_EVT_SENT: {
      Serial.print("EVT ARRIVED P"); Serial.println(curP);

      if(mode == 1){
        pendingDec = DEC_NONE;
        tMark = millis();
        rm = RM_WAIT_DECISION;
      } else if(mode == 2){
        // scan-only
        curP++;
        rm = RM_SCAN_MOVE;
      } else {
        rm = RM_IDLE;
      }
    } break;

    // ======================================================
    // MODE 1 : DECISION & PICK
    // ======================================================
    case RM_WAIT_DECISION: {
      if(pendingDec == DEC_NONE){
        processDecisionTimeout();
        break;
      }

      if(pendingDec == DEC_PICK){
        Serial.print("[MODE1] PICK P"); Serial.println(curP);
        rm = RM_DO_PICK;
      } else {
        Serial.print("[MODE1] SKIP P"); Serial.println(curP);
        curP++;
        rm = RM_SCAN_MOVE;
      }
      pendingDec = DEC_NONE;
    } break;

    case RM_DO_PICK: {
      pickFromHereToBin();
      if(stopReq) break;

      curP++;
      if(curP <= 9){
        Serial.print("[MODE1] RAPID -> P"); Serial.println(curP);
        moveXY_rapid(PX(curP), PY(curP));
        tMark = millis();
        rm = RM_SCAN_SETTLE;
      } else {
        Serial.println("[MODE1] DONE -> HOME");
        homeAll();
        rm = RM_IDLE;
      }
    } break;

    // ======================================================
    // MODE 2 : PICK FROM LIST
    // ======================================================
    case RM_MODE2_PICK_GOTO: {
      if(pickIdx >= pickCount){
        Serial.println("[MODE2] DONE -> HOME");
        homeAll();
        rm = RM_IDLE;
        break;
      }

      uint8_t p = pickList[pickIdx];
      Serial.print("[MODE2] GOTO P"); Serial.println(p);

      moveXY_rapid(PX(p), PY(p));   // hoặc rapid
      rm = RM_MODE2_PICK_DO;       // 🔥 GẮP NGAY
    } break;

    case RM_MODE2_PICK_DO: {
      Serial.print("[MODE2] PICK P"); Serial.println(pickList[pickIdx]);
      pickFromHereToBin();
      if(stopReq) break;

      pickIdx++;
      rm = RM_MODE2_PICK_GOTO;
    } break;

    // ======================================================
    // MODE 3 : MANUAL
    // ======================================================
    case RM_MODE3_WAIT_GOTO: {
      Serial.print("[MODE3] GOTO P"); Serial.println(mode3TargetP);
      moveXY_rapid(PX(mode3TargetP), PY(mode3TargetP));
      rm = RM_IDLE;
    } break;

    case RM_MODE3_DO_PICK: {
      pickFromHereToBin();
      homeAll();
      rm = RM_IDLE;
    } break;

    default:
      rm = RM_IDLE;
      break;
  }
}

// ============================================================
// ================= COMMAND PARSER ============================
// ============================================================
void parseListLine(const String& line){
  // "LIST P2 P5 P7"
  if(!homed){
    Serial.println("[ERR] Not homed. Send H0 first.");
    return;
  }
  if(stopReq){
    Serial.println("[ERR] STOP active. Send UNSTOP first.");
    return;
  }

  pickCount = 0;
  pickIdx = 0;

  for(int i=0; i<line.length() && pickCount < 9; i++){
    if(line[i]=='P' || line[i]=='p'){
      if(i+1 < line.length()){
        char c = line[i+1];
        if(c>='1' && c<='9'){
          pickList[pickCount++] = (uint8_t)(c - '0');
        }
      }
    }
  }

  Serial.print("[MODE2] PickCount="); Serial.println(pickCount);

  if(pickCount == 0){
    Serial.println("[MODE2] Empty list -> (stay IDLE)");
    rm = RM_IDLE;
  } else {
    rm = RM_MODE2_PICK_GOTO;
  }
}

void handleCommand(const String& cmdRaw){
  String cmd = cmdRaw;
  cmd.trim();
  if(cmd.length()==0) return;

  // STOP / UNSTOP
  if(cmd.equalsIgnoreCase("STOP")){
    stopReq = true;
    Serial.println("[STOP] Emergency stop!");
    return;
  }
  if(cmd.equalsIgnoreCase("UNSTOP")){
    stopReq = false;
    Serial.println("[STOP] Cleared stop.");
    return;
  }

  // OFFSET dx dy
  if(cmd.startsWith("OFFSET") || cmd.startsWith("offset")){
    float dx=0, dy=0;
    int ok = sscanf(cmd.c_str(), "OFFSET %f %f", &dx, &dy);
    if(ok==2){
      deltaX = dx;
      deltaY = dy;
      Serial.print("[CFG] OFFSET dx="); Serial.print(deltaX,2);
      Serial.print(" dy="); Serial.println(deltaY,2);
    }else{
      Serial.println("[CFG] Use: OFFSET dx dy");
    }
    return;
  }

  // H0
  if(cmd.equalsIgnoreCase("H0") || cmd.equalsIgnoreCase("HOME")){
    stopReq = false;
    homeAll();
    return;
  }

  // MODE n
  if(cmd.startsWith("MODE") || cmd.startsWith("mode")){
    int m=0;
    int ok = sscanf(cmd.c_str(), "MODE %d", &m);
    if(ok==1 && (m==1||m==2||m==3)){
      mode = m;
      Serial.print("[CFG] MODE="); Serial.println(mode);
    }else{
      Serial.println("[CFG] Use: MODE 1|2|3");
    }
    return;
  }

  // START
  // - MODE1: START = run live pick
  // - MODE2: START = SCAN only (Python will use it for SCAN command)
  // - MODE2 PICK is triggered by LIST (Python sends LIST on user's START)
  if(cmd.equalsIgnoreCase("START")){
    startRun();
    return;
  }

  // Decision from Python (mode1 only; mode2 scan ignores)
  if(cmd.startsWith("DEC") || cmd.startsWith("dec")){
    if(mode != 1) return; // ignore in mode2
    if(cmd.indexOf("PICK") >= 0 || cmd.indexOf("pick") >= 0){
      pendingDec = DEC_PICK;
    }else{
      pendingDec = DEC_SKIP;
    }
    return;
  }

  // MODE2 list (allow when idle too)
  if(cmd.startsWith("LIST") || cmd.startsWith("list")){
    if(mode == 2 && (rm == RM_IDLE || rm == RM_MODE2_PICK_GOTO || rm == RM_MODE2_PICK_DO)){
      // allow re-list only when idle; if running, user should stop first
      if(rm != RM_IDLE){
        Serial.println("[ERR] MODE2 busy. STOP then UNSTOP to reset.");
        return;
      }
      parseListLine(cmd);
    } else if(mode == 2 && rm == RM_IDLE){
      parseListLine(cmd);
    }
    return;
  }

  // MODE3 manual commands (unchanged)
  if(mode == 3){
    if(cmd.startsWith("GOTO") || cmd.startsWith("goto")){
      for(int i=0;i<cmd.length();i++){
        if(cmd[i]=='P' || cmd[i]=='p'){
          char c = cmd[i+1];
          if(c>='1' && c<='9'){
            mode3TargetP = (uint8_t)(c - '0');
            Serial.print("[MODE3] SET TARGET P");
            Serial.println(mode3TargetP);
            rm = RM_MODE3_WAIT_GOTO;
          }
        }
      }
      return;
    }
    if(cmd.equalsIgnoreCase("PICKNOW")){
      rm = RM_MODE3_DO_PICK;
      return;
    }
  }

  Serial.print("[ERR] Unknown cmd: ");
  Serial.println(cmd);
}

// ================= SETUP/LOOP =================
void setup(){
  Serial.begin(115200);

  pinMode(X_ENA,OUTPUT); pinMode(X_DIR,OUTPUT); pinMode(X_PUL,OUTPUT);
  pinMode(Y_ENA,OUTPUT); pinMode(Y_DIR,OUTPUT); pinMode(Y_PUL,OUTPUT);
  pinMode(Z_ENA,OUTPUT); pinMode(Z_DIR,OUTPUT); pinMode(Z_PUL,OUTPUT);

  pinMode(X_LIMIT,INPUT_PULLUP);
  pinMode(Y_LIMIT,INPUT_PULLUP);
  pinMode(Z_LIMIT,INPUT_PULLUP);

  digitalWrite(X_ENA,LOW);
  digitalWrite(Y_ENA,LOW);
  digitalWrite(Z_ENA,LOW);

  gripper.attach(SERVO_PIN);
  gripper.write(SERVO_OPEN);

  stopReq = false;
  homed = false;

  Serial.println("=== ROBOT PICKER (Event-based) ===");
  Serial.println("Cmd: H0 | OFFSET dx dy | MODE 1/2/3");
  Serial.println("MODE1: START -> live pick (EVT + DEC)");
  Serial.println("MODE2: START -> scan-only (EVT + save JSON) -> HOME");
  Serial.println("MODE2 pick: Python sends LIST P.. (trigger pick)");
  Serial.println("MODE3: GOTO Pn + PICKNOW");
  Serial.println();
}

void loop(){
  serialPoll();

  String line;
  if(takeLine(line)){
    handleCommand(line);
  }

  runStateMachine();
}