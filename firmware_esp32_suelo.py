# Firmware para Nodo AgroSpectra ESP32 (Agricultura de Precisión)
# Dispositivo: ESP32 DevKit V1 / WROOM-32
# Comunicación de Sensores: RS485 Modbus RTU (MAX485 / TTL to RS485)
# Sonda: Sensor Agrícola 3-en-1 o 7-en-1 (Humedad VWC, Temperatura y Conductividad Eléctrica EC)

"""
DIAGRAMA DE CONEXIÓN FÍSICA:
----------------------------
ESP32                    Módulo MAX485 (TTL-RS485)       Sensor Suelo RS485
------                   -------------------------       ------------------
GPIO 16 (RX2) <--------> RO (Receiver Output)            
GPIO 17 (TX2) ---------> DI (Driver Input)
GPIO 4        ---------> DE y RE unidos (Control TX/RX)
VIN (5V)      ---------> VCC
GND           ---------> GND                            
                         A (+)  ------------------------> Cable Amarillo (A+)
                         B (-)  ------------------------> Cable Azul (B-)
                         GND    ------------------------> Cable Negro (GND)
Alimentación externa 12V -------------------------------> Cable Marrón (VCC 9-24V)
"""

CÓDIGO_ARDUINO_ESP32 = """
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// --- PINES DE COMUNICACIÓN RS485 ---
#define RXD2 16
#define TXD2 17
#define RE_DE 4

// --- CONFIGURACIÓN DE RED WIFI / APN ---
const char* ssid = "TU_WIFI_RANCH";
const char* password = "TU_PASSWORD";
const char* serverApiUrl = "http://tu-servidor-agrospectra.com/api/telemetria";

// Parámetros de la Parcela
const char* PREDIO_ID = "predio_los_encinos_01";
const char* DISPOSITIVO_ID = "nodo_esp32_suelo_01";

// Trama Modbus RTU estándar para consultar Sensor de Suelo 3-en-1
// Dirección de esclavo: 0x01 | Función: 0x03 | Inicio: 0x0000 | Cantidad: 3 registros | CRC16
const byte requestBytes[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x03, 0x05, 0xCB};
byte responseBytes[11];

void setup() {
  Serial.begin(115200);
  Serial2.begin(4800, SERIAL_8N1, RXD2, TXD2); // Velocidad estándar del sensor agrícola Modbus
  
  pinMode(RE_DE, OUTPUT);
  digitalWrite(RE_DE, LOW); // Modo recepción

  Serial.println("Iniciando Nodo AgroSpectra...");
  
  // Conectar WiFi
  WiFi.begin(ssid, password);
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(500);
    Serial.print(".");
    intentos++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\\nWiFi Conectado!");
  } else {
    Serial.println("\\nOperando en modo sin conexión temporal.");
  }

  // Realizar lectura y envío
  tomarLecturaYEnviar();

  // Entrar en modo Deep Sleep para ahorro de batería (Ej. despertar cada 30 minutos)
  Serial.println("Entrando en Deep Sleep por 30 minutos...");
  esp_sleep_enable_timer_wakeup(30ULL * 60ULL * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() {
  // En Deep Sleep loop() nunca se ejecuta
}

void tomarLecturaYEnviar() {
  // 1. Enviar solicitud al sensor RS485
  digitalWrite(RE_DE, HIGH); // Habilitar Transmisión
  delay(10);
  Serial2.write(requestBytes, sizeof(requestBytes));
  Serial2.flush();
  digitalWrite(RE_DE, LOW);  // Regresar a Modo Recepción
  
  delay(100); // Esperar respuesta del sensor

  // 2. Leer respuesta
  if (Serial2.available() >= 7) {
    int bytesLeidos = Serial2.readBytes(responseBytes, 11);
    
    if (bytesLeidos >= 7 && responseBytes[0] == 0x01 && responseBytes[1] == 0x03) {
      // Decodificación de registros Modbus (formato de 16 bits)
      float humedad = ((responseBytes[3] << 8) | responseBytes[4]) / 10.0;     // % Humedad Volumétrica (VWC)
      float temperatura = ((responseBytes[5] << 8) | responseBytes[6]) / 10.0; // °C Temperatura Suelo
      int conductividad = (responseBytes[7] << 8) | responseBytes[8];          // uS/cm Salinidad / Fertilidad

      Serial.println("--- Lectura Exitosa de Suelo ---");
      Serial.printf("Humedad: %.1f %%\\n", humedad);
      Serial.printf("Temperatura: %.1f C\\n", temperatura);
      Serial.printf("Conductividad (EC): %d uS/cm\\n", conductividad);

      // 3. Enviar a servidor AgroSpectra
      if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(serverApiUrl);
        http.addHeader("Content-Type", "application/json");

        StaticJsonDocument<256> doc;
        doc["predio_id"] = PREDIO_ID;
        doc["dispositivo_id"] = DISPOSITIVO_ID;
        doc["humedad_suelo_vwc"] = humedad;
        doc["temperatura_suelo_c"] = temperatura;
        doc["conductividad_ec_us_cm"] = conductividad;
        doc["bateria_v"] = 3.92; // Lectura de pin analógico ADC

        String jsonPayload;
        serializeJson(doc, jsonPayload);

        int httpResponseCode = http.POST(jsonPayload);
        Serial.printf("Respuesta Servidor HTTP: %d\\n", httpResponseCode);
        http.end();
      }
    }
  } else {
    Serial.println("Aviso: Sonda RS485 no respondió. Verificar cableado de 12V y líneas A/B.");
  }
}
"""
