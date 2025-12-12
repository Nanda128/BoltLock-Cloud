/*
 * ESP32 MQTT Integration for BoltLock
 * 
 * This code shows how to integrate MQTT into the existing BoltLock firmware
 * Add this to your network_handler.c file
 */

#include "mqtt_client.h"
#include "esp_log.h"
#include "cJSON.h"

static const char* TAG = "MQTT";
static esp_mqtt_client_handle_t mqtt_client = NULL;
static bool mqtt_connected = false;

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, 
                                int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;
    
    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT Connected");
            mqtt_connected = true;
            
            esp_mqtt_client_subscribe(mqtt_client, MQTT_TOPIC_COMMAND, 0);
            ESP_LOGI(TAG, "Subscribed to %s", MQTT_TOPIC_COMMAND);
            
            publish_status();
            break;
            
        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGI(TAG, "MQTT Disconnected");
            mqtt_connected = false;
            break;
            
        case MQTT_EVENT_DATA:
            ESP_LOGI(TAG, "MQTT Data received on topic: %.*s", 
                    event->topic_len, event->topic);
            
            if (strncmp(event->topic, MQTT_TOPIC_COMMAND, event->topic_len) == 0) {
                handle_mqtt_command(event->data, event->data_len);
            }
            break;
            
        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "MQTT Error");
            break;
            
        default:
            break;
    }
}

esp_err_t mqtt_init(void) {
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = MQTT_BROKER_URI,
        .broker.address.port = MQTT_PORT,
    };
    
    mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (mqtt_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client");
        return ESP_FAIL;
    }
    
    esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID, 
                                    mqtt_event_handler, NULL);
    
    esp_err_t ret = esp_mqtt_client_start(mqtt_client);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client");
        return ret;
    }
    
    ESP_LOGI(TAG, "MQTT client started");
    return ESP_OK;
}

void publish_status(void) {
    if (!mqtt_connected) {
        return;
    }
    
    lock_state_t lock_state = get_lock_state();
    door_state_t door_state = get_door_state();
    
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", "esp32_001"); 
    
    const char* lock_str = (lock_state == LOCK_STATE_LOCKED) ? "LOCKED" : "UNLOCKED";
    cJSON_AddStringToObject(root, "lock_state", lock_str);
    
    const char* door_str = (door_state == DOOR_CLOSED) ? "CLOSED" : "OPEN";
    cJSON_AddStringToObject(root, "door_state", door_str);
    
    cJSON_AddBoolToObject(root, "wifi_connected", is_network_connected());
    
    char *json_str = cJSON_PrintUnformatted(root);
    
    esp_mqtt_client_publish(mqtt_client, MQTT_TOPIC_STATUS, json_str, 0, 0, 0);
    ESP_LOGI(TAG, "Published status: %s", json_str);
    
    free(json_str);
    cJSON_Delete(root);
}

void publish_event(const char* event_type, const char* description) {
    if (!mqtt_connected) {
        return;
    }
    
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", "esp32_001");
    cJSON_AddStringToObject(root, "event_type", event_type);
    cJSON_AddStringToObject(root, "description", description);
    
    char *json_str = cJSON_PrintUnformatted(root);
    
    esp_mqtt_client_publish(mqtt_client, MQTT_TOPIC_EVENTS, json_str, 0, 0, 0);
    ESP_LOGI(TAG, "Published event: %s", json_str);
    
    free(json_str);
    cJSON_Delete(root);
}

static void handle_mqtt_command(char* data, int data_len) {
    cJSON *root = cJSON_ParseWithLength(data, data_len);
    if (root == NULL) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }
    
    cJSON *action = cJSON_GetObjectItem(root, "action");
    if (action == NULL || !cJSON_IsString(action)) {
        ESP_LOGE(TAG, "Invalid command format");
        cJSON_Delete(root);
        return;
    }
    
    if (strcmp(action->valuestring, "lock") == 0) {
        ESP_LOGI(TAG, "Received remote lock command");
        send_sm_event(SM_EVENT_REMOTE_LOCK, NULL);
        publish_event("REMOTE_LOCK", "Lock command received");
        
    } else if (strcmp(action->valuestring, "unlock") == 0) {
        ESP_LOGI(TAG, "Received remote unlock command");
        send_sm_event(SM_EVENT_REMOTE_UNLOCK, NULL);
        publish_event("REMOTE_UNLOCK", "Unlock command received");
        
    } else {
        ESP_LOGW(TAG, "Unknown action: %s", action->valuestring);
    }
    
    cJSON_Delete(root);
    
    vTaskDelay(pdMS_TO_TICKS(500));
    publish_status();
}

void notify_state_change(void) {
    publish_status();
}

/*
 * Integration Instructions:
 * 
 * 1. Add to CMakeLists.txt in main component:
 *    REQUIRES mqtt json
 * 
 * 2. In config.h, add:
 *    #define MQTT_BROKER_URI "mqtt://YOUR_SERVER_IP:1883"
 * 
 * 3. In main.c app_main(), after network_init():
 *    ret = mqtt_init();
 *    if (ret != ESP_OK) {
 *        ESP_LOGW(TAG, "MQTT initialization failed");
 *    }
 * 
 * 4. In event_logger.c log_event(), add:
 *    publish_event(event_type_names[type], description);
 * 
 * 5. In lock_control.c, after state changes:
 *    notify_state_change();
 */
