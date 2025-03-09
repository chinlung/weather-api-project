import httpx
import os
import json
import logging
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List

load_dotenv()

# Setup logging with debug level
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Add console handler if not already present
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

class CWAWeatherAPI:
    """Client for the Central Weather Administration (CWA) Open Data API."""
    
    BASE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the CWA API client.
        
        Args:
            api_key: API key for the CWA API. If not provided, will be loaded from environment.
        """
        self.api_key = api_key or os.getenv("CWA_API_KEY")
        if not self.api_key:
            raise ValueError("CWA API key is required. Set it in the .env file or pass it explicitly.")
        
        # 記錄 API 金鑰的前幾個字符（出於安全考慮不記錄完整金鑰）
        masked_key = self.api_key[:8] + "..." if self.api_key else "None"
        logger.info(f"初始化 CWA API 客戶端，API 金鑰: {masked_key}")
    
    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to the CWA API.
        
        Args:
            endpoint: API endpoint to call
            params: Optional query parameters
            
        Returns:
            API response JSON as a dictionary
        """
        url = f"{self.BASE_URL}/{endpoint}"
        request_params = {"Authorization": self.api_key}
        if params:
            request_params.update(params)
            
        logger.info(f"發送請求到 {url}")
        logger.debug(f"請求參數: {request_params}")
            
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=request_params)
                logger.info(f"API 回應狀態碼: {response.status_code}")
                
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP 請求失敗: {e}")
                    return {"error": f"HTTP 錯誤: {e}"}
                
                try:
                    # 讀取完整的回應內容
                    content = response.text
                    
                    # 檢查回應內容是否為空
                    if not content.strip():
                        logger.error("API 回應內容為空")
                        return {"error": "空的 API 回應"}
                    
                    # 嘗試解析 JSON
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON 解析錯誤: {str(e)}\n回應內容: {content[:200]}...")
                        return {"error": f"JSON 解析錯誤: {str(e)}"}
                    
                    # 驗證資料結構
                    if not isinstance(data, dict):
                        error_msg = f"無效的回應格式: 預期 dict，得到 {type(data)}"
                        logger.error(error_msg)
                        return {"error": error_msg}
                    
                    # 檢查 success 欄位
                    if "success" in data and not data["success"]:
                        error_msg = data.get("message", "未知 API 錯誤")
                        logger.error(f"API 返回失敗: {error_msg}")
                        return {"error": f"API 錯誤: {error_msg}"}
                    
                    # 檢查並處理 records
                    if "records" in data:
                        if not data["records"]:
                            logger.warning("回應中 records 為空")
                            return {"error": "無資料"}
                            
                        # 處理可能的換行符號
                        if isinstance(data["records"], dict):
                            for key, value in data["records"].items():
                                if isinstance(value, str):
                                    data["records"][key] = value.replace("\\n", "\n").replace("\r\n", "\n")
                    else:
                        logger.error("回應中缺少 records 欄位")
                        return {"error": "無效的回應: 缺少 records 欄位"}
                    
                    return data
                    
                except Exception as e:
                    logger.error(f"處理回應時發生錯誤: {str(e)}")
                    return {"error": f"處理回應錯誤: {str(e)}"}
                    
            except httpx.TimeoutException:
                logger.error("請求超時")
                return {"error": "請求超時"}
            except Exception as e:
                logger.error(f"請求時發生錯誤: {str(e)}")
                return {"error": f"請求錯誤: {str(e)}"}
    
    async def get_weather_forecast(self, location: str = None, element: str = None, forecast_type: str = "36h") -> Dict[str, Any]:
        """Get weather forecast data from CWA API.
        
        Args:
            location: Optional location name to filter results (e.g. 臺北市, 高雄市)
            element: Optional weather element to filter results
            forecast_type: Type of forecast to retrieve, either "36h" for 36-hour forecast (F-C0032-001)
                           or "7d" for 7-day forecast (F-D0047-091)
            
        Returns:
            Weather forecast data
        """
        # 初始化參數字典
        params = {
            "format": "JSON",  # 指定返回格式為 JSON
            "sort": "time"     # 結果按時間排序
        }
        
        # 處理地點參數 (如果指定)
        if location:
            # 確保正確的地名格式
            location = location.strip()
            params["locationName"] = location
            logger.info(f"獲取天氣預報，地點: {location}")
        else:
            logger.info("獲取全部地區天氣預報")
            
        # 處理氣象要素參數 (如果指定)
        if element:
            params["elementName"] = element
        
        # 根據 forecast_type 選擇適當的 API 端點
        if forecast_type == "36h":
            # 36小時天氣預報
            endpoint = "F-C0032-001"
            logger.info(f"使用36小時天氣預報端點: {endpoint}")
        else:
            # 7天天氣預報
            endpoint = "F-D0047-091"
            logger.info(f"使用7天天氣預報端點: {endpoint}")
            
        logger.info(f"使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            # 檢查是否有錯誤訊息
            if "error" in data:
                return data
            
            # 驗證回應結構
            if "records" not in data:
                logger.error(f"API 回應中缺少 records 欄位: {data}")
                return {"error": "無效的 API 回應: 缺少 records 欄位"}
            
            # 記錄找到的地點 (處理不同的 API 回應格式)
            if "location" in data["records"]:
                locations = data["records"]["location"]
                loc_names = [loc.get("locationName", "未知") for loc in locations[:5]]
                logger.info(f"找到的地點: {', '.join(loc_names)}{' 等...' if len(locations) > 5 else ''}")
            
            # 檢查是否使用新的 API 格式 (Locations)
            if "Locations" in data["records"]:
                if "Location" in data["records"]["Locations"]:
                    locations = data["records"]["Locations"]["Location"]
                    loc_names = [loc.get("locationName", "未知") for loc in locations[:5]]
                    logger.info(f"找到的地點 (新格式): {', '.join(loc_names)}{' 等...' if len(locations) > 5 else ''}")
            
            # 如果指定了地點但沒有找到匹配的資料
            if location and "location" in data["records"]:
                if not any(location in loc.get("locationName", "") for loc in data["records"]["location"]):
                    logger.warning(f"未找到匹配地點 '{location}' 的天氣預報")
            
            return data
            
        except Exception as e:
            logger.error(f"取得天氣預報時發生錯誤: {str(e)}")
            return {"error": str(e)}
    
    async def get_weather_warnings(self, hazard_type: str = None, location: str = None) -> Dict[str, Any]:
        """Get active weather warnings.
        
        Args:
            hazard_type: Optional hazard type to filter results (e.g. 濃霧, 大雨, 豪雨)
            location: Optional location name to filter results
        
        Returns:
            Active weather warning data
        """
        params = {
            "format": "JSON"
        }
        
        # 處理災害類型參數 (如果指定)
        if hazard_type:
            params["phenomena"] = hazard_type
            logger.info(f"獲取天氣警特報，災害類型: {hazard_type}")
        
        # 處理地點參數 (如果指定)
        if location:
            params["locationName"] = location
            logger.info(f"獲取天氣警特報，地點: {location}")
        
        endpoint = "W-C0033-001"
        logger.info(f"獲取天氣警特報，使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            if "error" in data:
                return data
                
            if "records" not in data:
                logger.error("警特報回應中缺少 records 欄位")
                return {"error": "無效的 API 回應: 缺少 records 欄位"}
            
            # 檢查是否有警特報資料
            if "record" in data["records"]:
                warnings = data["records"]["record"]
                if warnings:
                    warning_count = len(warnings)
                    logger.info(f"找到 {warning_count} 筆警特報資料")
                    
                    # 記錄前幾筆警特報的基本資訊
                    for i, warning in enumerate(warnings[:3]):
                        hazard = warning.get("phenomena", "未知")
                        locations = warning.get("locationName", [])
                        location_str = ", ".join(locations[:3])
                        if len(locations) > 3:
                            location_str += " 等..."
                        logger.info(f"警特報 {i+1}: {hazard} - 影響地區: {location_str}")
                else:
                    logger.info("目前無警特報資料")
            else:
                logger.warning("警特報回應中缺少 record 欄位")
                
            return data
        except Exception as e:
            logger.error(f"取得天氣警特報時發生錯誤: {str(e)}")
            return {"error": str(e)}
    
    async def get_rainfall_data(self, location: str = None) -> Dict[str, Any]:
        """Get rainfall observation data.
        
        Args:
            location: Optional location name to filter results
            
        Returns:
            Rainfall observation data
        """
        params = {}
        if location:
            params["locationName"] = location.strip()
            logger.info(f"獲取雨量觀測資料，地點: {location}")
        else:
            logger.info("獲取全部雨量觀測資料")
            
        endpoint = "O-A0002-001"
        logger.info(f"使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            if "error" in data:
                return data
                
            if "records" not in data:
                logger.error("雨量資料回應中缺少 records 欄位")
                return {"error": "無效的 API 回應: 缺少 records 欄位"}
                
            return data
        except Exception as e:
            logger.error(f"取得雨量資料時發生錯誤: {str(e)}")
            return {"error": str(e)}
    
    async def get_weather_observation(self, location: str = None) -> Dict[str, Any]:
        """Get current weather observation data.
        
        Args:
            location: Optional location name to filter results
            
        Returns:
            Current weather observation data
        """
        params = {
            "format": "JSON"
        }
        if location:
            location = location.strip()
            # 如果提供了地點，我們可以使用 StationName 參數進行過濾
            # 但由於 API 可能需要更靈活的匹配，我們也會在後續處理中進行過濾
            params["StationName"] = location
            logger.info(f"獲取氣象觀測資料，地點: {location}")
        else:
            logger.info("獲取全部氣象觀測資料")
            
        endpoint = "O-A0003-001"
        logger.info(f"使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            if "error" in data:
                return data
                
            if "records" not in data:
                logger.error("氣象觀測資料回應中缺少 records 欄位")
                return {"error": "無效的 API 回應: 缺少 records 欄位"}
                
            # 檢查並轉換 Station 資料
            if "records" in data and "Station" in data["records"]:
                stations = data["records"]["Station"]
                station_names = [station.get("StationName", "未知") for station in stations[:5]]
                logger.info(f"找到的觀測站: {', '.join(station_names)}{' 等...' if len(stations) > 5 else ''}")
                
                # 重新組織資料結構以符合其他 API 的格式
                data["records"]["location"] = []
                for station in stations:
                    # 檢查是否有觀測時間資訊
                    obs_time = "未知"
                    if "ObsTime" in station and "DateTime" in station["ObsTime"]:
                        obs_time = station["ObsTime"]["DateTime"]
                    
                    # 檢查地理資訊
                    county_name = "未知"
                    town_name = "未知"
                    if "GeoInfo" in station:
                        county_name = station["GeoInfo"].get("CountyName", "未知")
                        town_name = station["GeoInfo"].get("TownName", "未知")
                    
                    # 檢查天氣元素
                    weather_elements = {}
                    if "WeatherElement" in station:
                        we = station["WeatherElement"]
                        weather = we.get("Weather", "未知")
                        
                        # 獲取降雨量
                        precipitation = "未知"
                        if "Now" in we and "Precipitation" in we["Now"]:
                            precipitation = we["Now"]["Precipitation"]
                            if precipitation == -99.0 or precipitation == -990:
                                precipitation = "未知"
                        
                        # 獲取其他氣象資料
                        wind_direction = we.get("WindDirection", "未知")
                        if wind_direction == -99.0 or wind_direction == -990:
                            wind_direction = "未知"
                            
                        wind_speed = we.get("WindSpeed", "未知")
                        if wind_speed == -99.0 or wind_speed == -990:
                            wind_speed = "未知"
                            
                        air_temperature = we.get("AirTemperature", "未知")
                        if air_temperature == -99.0 or air_temperature == -990:
                            air_temperature = "未知"
                            
                        relative_humidity = we.get("RelativeHumidity", "未知")
                        if relative_humidity == -99 or relative_humidity == -990:
                            relative_humidity = "未知"
                            
                        air_pressure = we.get("AirPressure", "未知")
                        if air_pressure == -99.0 or air_pressure == -990:
                            air_pressure = "未知"
                        
                        # 獲取能見度描述
                        visibility = we.get("VisibilityDescription", "未知")
                        
                        # 獲取日照時數
                        sunshine_duration = we.get("SunshineDuration", "未知")
                        if sunshine_duration == -99.0 or sunshine_duration == -990:
                            sunshine_duration = "未知"
                        
                        # 獲取紫外線指數
                        uv_index = we.get("UVIndex", "未知")
                        if uv_index == -99.0 or uv_index == -990:
                            uv_index = "未知"
                        
                        weather_elements = {
                            "TEMP": air_temperature,
                            "HUMD": relative_humidity,
                            "PRES": air_pressure,
                            "WDIR": wind_direction,
                            "WDSD": wind_speed,
                            "24R": precipitation,
                            "Weather": weather,
                            "VisibilityDescription": visibility,
                            "SunshineDuration": sunshine_duration,
                            "UVIndex": uv_index
                        }
                    
                    # 建立位置資料
                    station_name = station.get("StationName", "未知")
                    full_location_name = f"{county_name}{town_name} {station_name}"
                    
                    # 如果指定了位置但不匹配，則跳過
                    if location:
                        # 更靈活的匹配邏輯
                        location_lower = location.lower()
                        county_lower = county_name.lower()
                        town_lower = town_name.lower()
                        station_lower = station_name.lower()
                        full_location_lower = full_location_name.lower()
                        
                        # 檢查是否為部分匹配
                        if (location_lower not in county_lower and 
                            location_lower not in town_lower and 
                            location_lower not in station_lower and
                            location_lower not in full_location_lower and
                            county_lower not in location_lower and
                            town_lower not in location_lower and
                            station_lower not in location_lower):
                            logger.debug(f"跳過不匹配的觀測站: {full_location_name} (搜尋: {location})")
                            continue
                        
                        logger.info(f"找到匹配的觀測站: {full_location_name} (搜尋: {location})")
                    
                    # 建立位置資料結構
                    location_data = {
                        "locationName": full_location_name,
                        "time": {"obsTime": obs_time},
                        "weatherElement": []
                    }
                    
                    # 添加天氣元素
                    for elem_name, elem_value in weather_elements.items():
                        location_data["weatherElement"].append({
                            "elementName": elem_name,
                            "elementValue": elem_value
                        })
                    
                    data["records"]["location"].append(location_data)
                
                # 記錄找到的匹配位置數量
                logger.info(f"找到 {len(data['records']['location'])} 個觀測站資料")
                
                if location and len(data["records"]["location"]) == 0:
                    logger.warning(f"未找到匹配地點 '{location}' 的觀測站")
            else:
                logger.error("回應中缺少 Station 資料")
                return {"error": "無效的回應: 缺少觀測站資料"}
            
            return data
        except Exception as e:
            logger.error(f"取得氣象觀測資料時發生錯誤: {str(e)}")
            return {"error": str(e)}