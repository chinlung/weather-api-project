import httpx
import os
import json
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List
from datetime import datetime
from logger_config import weather_api_logger as logger, api_requests_logger as api_logger

load_dotenv()

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
        
        # 建立請求 ID 和時間戳記
        request_id = f"{endpoint}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 記錄請求資訊到專門的日誌檔案
        masked_params = request_params.copy()
        if "Authorization" in masked_params:
            auth_value = masked_params["Authorization"]
            if auth_value and len(auth_value) > 8:
                masked_params["Authorization"] = auth_value[:8] + "..."
        
        api_logger.info(f"[請求 {request_id}] 端點: {endpoint}, URL: {url}")
        api_logger.debug(f"[請求 {request_id}] 參數: {masked_params}")
            
        logger.info(f"發送請求到 {url}")
        logger.debug(f"請求參數: {masked_params}")
            
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=request_params)
                logger.info(f"API 回應狀態碼: {response.status_code}")
                api_logger.info(f"[回應 {request_id}] 狀態碼: {response.status_code}")
                
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    error_msg = f"HTTP 請求失敗: {e}"
                    logger.error(error_msg)
                    api_logger.error(f"[回應 {request_id}] {error_msg}")
                    return {"error": f"HTTP 錯誤: {e}"}
                
                try:
                    # 讀取完整的回應內容
                    content = response.text
                    
                    # 記錄回應內容到專門的日誌檔案
                    content_preview = content[:500] + "..." if len(content) > 500 else content
                    api_logger.debug(f"[回應 {request_id}] 內容: {content_preview}")
                    
                    # 檢查回應內容是否為空
                    if not content.strip():
                        error_msg = "API 回應內容為空"
                        logger.error(error_msg)
                        api_logger.error(f"[回應 {request_id}] {error_msg}")
                        return {"error": "空的 API 回應"}
                    
                    # 嘗試解析 JSON
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError as e:
                        error_msg = f"JSON 解析錯誤: {str(e)}\n回應內容: {content[:200]}..."
                        logger.error(error_msg)
                        api_logger.error(f"[回應 {request_id}] {error_msg}")
                        return {"error": f"JSON 解析錯誤: {str(e)}"}
                    
                    # 驗證資料結構
                    if not isinstance(data, dict):
                        error_msg = f"無效的回應格式: 預期 dict，得到 {type(data)}"
                        logger.error(error_msg)
                        api_logger.error(f"[回應 {request_id}] {error_msg}")
                        return {"error": error_msg}
                    
                    # 檢查 success 欄位
                    if "success" in data and not data["success"]:
                        error_msg = data.get("message", "未知 API 錯誤")
                        logger.error(f"API 返回失敗: {error_msg}")
                        api_logger.error(f"[回應 {request_id}] API 返回失敗: {error_msg}")
                        return {"error": f"API 錯誤: {error_msg}"}
                    
                    # 檢查並處理 records
                    if "records" in data:
                        if not data["records"]:
                            logger.warning("回應中 records 為空")
                            api_logger.warning(f"[回應 {request_id}] 回應中 records 為空")
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
    
    async def get_weather_forecast(self, location: str = None, element: str = None, forecast_type: str = "36h", filter_response: bool = True, element_types: List[str] = None) -> Dict[str, Any]:
        """Get weather forecast data.
        
        Args:
            location: Optional location name to filter results
            element: Optional weather element to filter results
            forecast_type: Type of forecast, either "36h" or "7d"
            filter_response: Whether to filter the API response to only include relevant data
            element_types: List of weather element types to include in the response (七日預報專用)
                          如果未指定，七日預報預設只包含「天氣預報綜合描述」
                          可用的元素類型：平均溫度、最高溫度、最低溫度、平均露點溫度、平均相對濕度、
                                      最高體感溫度、最低體感溫度、最大舒適度指數、最小舒適度指數、
                                      風速、風向、12小時降雨機率、天氣現象、紫外線指數、天氣預報綜合描述
        
        Returns:
            Weather forecast data
        """
        """Get weather forecast data from CWA API.
        
        Args:
            location: Optional location name to filter results (e.g. 臺北市, 高雄市)
            element: Optional weather element to filter results
            forecast_type: Type of forecast to retrieve, either "36h" for 36-hour forecast (F-C0032-001)
                           or "7d" for 7-day forecast (F-D0047-091)
            filter_response: Whether to filter and simplify the API response (default: True)
            
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
            
            # 對於七日預報，允許使用 locationName 參數直接向 API 請求特定地點的資料
            # 但也將地點名稱保存以便後續過濾
            if "locationName" in params:
                target_location = params["locationName"]
                # 使用 locationName 參數直接向 API 請求特定地點的資料
                api_logger.info(f"七日預報請求，目標地點: {target_location}，已在請求中指定")
            else:
                target_location = None
                
            # 記錄七日預報的特殊處理
            api_logger.info(f"七日預報請求，地點: {location if location else '全臺灣'}，參數: {params}")
            
            # 記錄完整的參數資訊以便進行除錯
            api_logger.debug(f"七日預報完整參數: {params}")
            
        logger.info(f"使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            # 檢查是否有錯誤訊息
            if "error" in data:
                return data
                
            # 如果不需要過濾回應，直接返回原始資料
            if not filter_response:
                return data
            
            # 驗證回應結構
            if "records" not in data:
                logger.error(f"API 回應中缺少 records 欄位: {data}")
                api_logger.error(f"API 回應中缺少 records 欄位: {data}")
                return {"error": "無效的 API 回應: 缺少 records 欄位"}
            
            # 記錄 API 回應的基本結構
            api_logger.info(f"API回應基本結構: {list(data['records'].keys())}")
            
            # 處理不同的 API 回應格式
            if forecast_type != "36h" and "Locations" in data["records"]:
                # 七日預報的新格式
                locations_data = data["records"]["Locations"]
                api_logger.info(f"七日預報 Locations 欄位類型: {type(locations_data)}")
                
                # 如果需要過濾回應，創建一個簡化版的資料結構
                if filter_response:
                    filtered_data = {
                        "success": data.get("success", "true"),
                        "records": {
                            "Locations": []
                        }
                    }
                
                # 處理 Locations 為列表的情況
                if isinstance(locations_data, list) and locations_data:
                    # 取得第一個 Locations 項目
                    location_group = locations_data[0]
                    api_logger.info(f"七日預報結構: Locations[0] 包含 {list(location_group.keys())}")
                    
                    if "Location" in location_group:
                        locations = location_group["Location"]
                        loc_names = [loc.get("LocationName", "未知") for loc in locations[:5]]
                        logger.info(f"找到的地點 (七日預報): {', '.join(loc_names)}{' 等...' if len(locations) > 5 else ''}")
                        api_logger.info(f"找到 {len(locations)} 個地點資料 (七日預報)")
                        
                        # 如果需要過濾回應，創建一個簡化版的 Location 列表
                        if filter_response:
                            filtered_location_group = {
                                "DatasetDescription": location_group.get("DatasetDescription", ""),
                                "LocationsName": location_group.get("LocationsName", ""),
                                "Location": []
                            }
                        
                        # 如果指定了地點，檢查是否有匹配的資料
                        if location:
                            # 建立可能的地點名稱變體
                            location_variants = [location]
                            if '臺' in location:
                                location_variants.append(location.replace('臺', '台'))
                            elif '台' in location:
                                location_variants.append(location.replace('台', '臺'))
                            
                            # 如果沒有包含「市」或「縣」，嘗試添加
                            if not any(x in location for x in ['市', '縣']):
                                location_variants.extend([f"{loc}市" for loc in location_variants])
                                location_variants.extend([f"{loc}縣" for loc in location_variants])
                            
                            api_logger.info(f"嘗試匹配的地點名稱變體: {location_variants}")
                            
                            # 使用更靈活的匹配邏輯
                            matched_locations = []
                            for loc in locations:
                                loc_name = loc.get("LocationName", "")
                                # 檢查是否有任何變體匹配
                                if any(variant in loc_name or loc_name in variant for variant in location_variants):
                                    matched_locations.append(loc)
                                    api_logger.info(f"找到匹配地點: {loc_name}")
                                    # 檢查天氣元素是否為空，支援不同的欄位名稱格式
                                    weather_elements = []
                                    for field_name in ["weatherElement", "WeatherElement"]:
                                        if field_name in loc and loc[field_name]:
                                            weather_elements = loc[field_name]
                                            api_logger.info(f"地點 {loc_name} 使用 {field_name} 欄位")
                                            break
                                    
                                    if not weather_elements:
                                        api_logger.warning(f"地點 {loc_name} 的天氣元素為空")
                            
                            if not matched_locations:
                                api_logger.warning(f"未找到匹配地點 '{location}' 的七日預報資料")
                                # 輸出所有可用的地點名稱（前10個）
                                available_locations = [loc.get("LocationName", "未知") for loc in locations[:10]]
                                api_logger.info(f"可用的地點名稱（前10個）: {available_locations}")
                            else:
                                api_logger.info(f"找到匹配地點 '{location}' 的七日預報資料: {[loc.get('LocationName') for loc in matched_locations]}")
                                
                                # 如果需要過濾回應，只保留匹配的地點資料
                                if filter_response:
                                    # 如果是七日預報且需要過濾元素類型
                                    if forecast_type != "36h" and matched_locations:
                                        # 預設只保留「天氣預報綜合描述」
                                        if element_types is None:
                                            element_types = ["天氣預報綜合描述"]
                                            
                                        # 記錄要保留的元素類型
                                        api_logger.info(f"七日預報只保留以下元素類型: {element_types}")
                                        
                                        # 過濾每個地點的天氣元素
                                        for loc in matched_locations:
                                            # 檢查天氣元素欄位名稱，可能是 WeatherElement 或 weatherElement
                                            for field_name in ["WeatherElement", "weatherElement"]:
                                                if field_name in loc and loc[field_name]:
                                                    # 確定元素名稱欄位
                                                    if loc[field_name] and len(loc[field_name]) > 0:
                                                        # 檢查元素名稱欄位的可能大小寫形式
                                                        element_name_field = None
                                                        for name_field in ["ElementName", "elementName"]:
                                                            if name_field in loc[field_name][0]:
                                                                element_name_field = name_field
                                                                api_logger.info(f"使用元素名稱欄位: {name_field}")
                                                                break
                                                        
                                                        if element_name_field is None:
                                                            api_logger.warning(f"無法確定元素名稱欄位，跳過過濾元素")
                                                            continue
                                                        
                                                        # 只保留指定的元素類型
                                                        filtered_elements = []
                                                        for elem in loc[field_name]:
                                                            if elem.get(element_name_field) in element_types:
                                                                filtered_elements.append(elem)
                                                        
                                                        # 替換原始的天氣元素列表
                                                        loc[field_name] = filtered_elements
                                                        
                                                        # 記錄過濾後的元素數量
                                                        api_logger.info(f"過濾後保留 {len(loc[field_name])} 個天氣元素")
                                                
                                                # 添加可用的元素類型資訊
                                                if "available_element_types" not in filtered_data:
                                                    # 從原始資料中獲取所有可用的元素類型
                                                    all_elements = []
                                                    for orig_loc in locations:
                                                        # 檢查天氣元素欄位名稱，可能是 WeatherElement 或 weatherElement
                                                        for field_name in ["WeatherElement", "weatherElement"]:
                                                            if field_name in orig_loc and orig_loc[field_name]:
                                                                # 檢查元素名稱欄位的可能大小寫形式
                                                                element_name_field = None
                                                                for name_field in ["ElementName", "elementName"]:
                                                                    if name_field in orig_loc[field_name][0]:
                                                                        element_name_field = name_field
                                                                        break
                                                                
                                                                if element_name_field is not None:
                                                                    all_elements.extend([elem.get(element_name_field) for elem in orig_loc[field_name]])
                                                    
                                                    # 去除重複的元素類型和 None 值
                                                    filtered_data["available_element_types"] = list(set([e for e in all_elements if e]))
                                    
                                    filtered_location_group["Location"] = matched_locations
                                    filtered_data["records"]["Locations"] = [filtered_location_group]
                    else:
                        api_logger.warning(f"七日預報 Locations[0] 中缺少 Location 欄位")
                        
                        # 如果需要過濾回應但缺少 Location 欄位，返回錯誤
                        if filter_response:
                            return {"error": "七日預報資料結構異常: 缺少 Location 欄位"}
                # 處理 Locations 為字典的情況 (老版格式)
                elif isinstance(locations_data, dict) and "Location" in locations_data:
                    locations = locations_data["Location"]
                    loc_names = [loc.get("locationName", "未知") for loc in locations[:5]]
                    logger.info(f"找到的地點 (七日預報老格式): {', '.join(loc_names)}{' 等...' if len(locations) > 5 else ''}")
                    api_logger.info(f"找到 {len(locations)} 個地點資料 (七日預報老格式)")
                else:
                    api_logger.warning(f"七日預報回應中 Locations 結構異常")
                    
                    # 如果需要過濾回應但 Locations 結構異常，返回錯誤
                    if filter_response:
                        return {"error": "七日預報資料結構異常: Locations 格式不正確"}
            elif "location" in data["records"]:
                # 36小時預報的標準格式
                locations = data["records"]["location"]
                loc_names = [loc.get("locationName", "未知") for loc in locations[:5]]
                logger.info(f"找到的地點: {', '.join(loc_names)}{' 等...' if len(locations) > 5 else ''}")
                api_logger.info(f"找到 {len(locations)} 個地點資料")
            
            # 如果是七日預報且已經過濾了回應，返回過濾後的資料
            if forecast_type != "36h" and filter_response and "filtered_data" in locals():
                return filtered_data
                
            # 處理36小時預報資料
            if forecast_type == "36h" and "location" in data["records"]:
                locations = data["records"]["location"]
                matched_locations = []
                
                # 如果指定了地點，找出匹配的地點資料
                if location:
                    location_variants = [location]
                    if '臺' in location:
                        location_variants.append(location.replace('臺', '台'))
                    elif '台' in location:
                        location_variants.append(location.replace('台', '臺'))
                    
                    # 如果沒有包含「市」或「縣」，嘗試添加
                    if not any(x in location for x in ['市', '縣']):
                        location_variants.extend([f"{loc}市" for loc in location_variants])
                        location_variants.extend([f"{loc}縣" for loc in location_variants])
                    
                    # 尋找匹配的地點
                    for loc in locations:
                        loc_name = loc.get("locationName", "")
                        if any(variant in loc_name or loc_name in variant for variant in location_variants):
                            matched_locations.append(loc)
                    
                    if not matched_locations:
                        warning_msg = f"未找到匹配地點 '{location}' 的天氣預報"
                        logger.warning(warning_msg)
                        api_logger.warning(warning_msg)
                else:
                    # 如果沒有指定地點，使用所有地點資料
                    matched_locations = locations
                    
                    # 如果需要過濾回應，只保留第一個地點資料
                    if filter_response:
                        matched_locations = locations[:1]  # 只保留第一個地點
                
                # 解析匹配地點的天氣資料
                for loc in matched_locations:
                    loc_name = loc.get("locationName", "未知")
                    api_logger.info(f"解析 {loc_name} 的天氣預報資料")
                    
                    # 建立結構化的預報資料
                    parsed_forecast = {
                        "location": loc_name,
                        "forecasts": []
                    }
                    
                    # 從第一個天氣元素獲取所有時間區段
                    if "weatherElement" in loc and loc["weatherElement"]:
                        time_periods = []
                        first_element = loc["weatherElement"][0]
                        if "time" in first_element:
                            time_periods = first_element["time"]
                        
                        # 為每個時間區段建立預報資料結構
                        for period in time_periods:
                            start_time = period.get("startTime")
                            end_time = period.get("endTime")
                            
                            forecast_entry = {
                                "start_time": start_time,
                                "end_time": end_time,
                                "weather": None,
                                "weather_code": None,
                                "max_temperature": None,
                                "min_temperature": None,
                                "precipitation_probability": None,
                                "comfort_index": None
                            }
                            
                            # 解析每個天氣元素的資料
                            for element in loc["weatherElement"]:
                                elem_name = element.get("elementName")
                                # 找到對應時間區段的資料
                                for time_data in element["time"]:
                                    if time_data["startTime"] == start_time and time_data["endTime"] == end_time:
                                        param = time_data.get("parameter", {})
                                        
                                        if elem_name == "Wx":
                                            forecast_entry["weather"] = param.get("parameterName")
                                            forecast_entry["weather_code"] = param.get("parameterValue")
                                        elif elem_name == "PoP":
                                            try:
                                                prob = float(param.get("parameterName", "0"))
                                                forecast_entry["precipitation_probability"] = max(0, min(100, prob))
                                            except (ValueError, TypeError):
                                                forecast_entry["precipitation_probability"] = None
                                        elif elem_name == "MinT":
                                            try:
                                                temp = float(param.get("parameterName", "0"))
                                                forecast_entry["min_temperature"] = temp
                                            except (ValueError, TypeError):
                                                forecast_entry["min_temperature"] = None
                                        elif elem_name == "MaxT":
                                            try:
                                                temp = float(param.get("parameterName", "0"))
                                                forecast_entry["max_temperature"] = temp
                                            except (ValueError, TypeError):
                                                forecast_entry["max_temperature"] = None
                                        elif elem_name == "CI":
                                            forecast_entry["comfort_index"] = param.get("parameterName")
                            
                            parsed_forecast["forecasts"].append(forecast_entry)
                    
                    # 將解析後的資料加入回傳結果
                    if "parsed_forecasts" not in data:
                        data["parsed_forecasts"] = []
                    data["parsed_forecasts"].append(parsed_forecast)
            
            # 如果是七日預報但沒有資料，記錄更詳細的資訊
            if forecast_type != "36h" and "Locations" not in data["records"]:
                error_msg = f"七日預報回應缺少 Locations 欄位: {data['records']}"
                logger.error(error_msg)
                api_logger.error(error_msg)
                # 記錄更多資訊以協助除錯
                api_logger.debug(f"完整的七日預報回應: {data}")
                return {"error": error_msg}
            elif forecast_type != "36h" and isinstance(data["records"]["Locations"], list) and not data["records"]["Locations"]:
                error_msg = f"七日預報 Locations 欄位為空列表: {data['records']}"
                logger.error(error_msg)
                api_logger.error(error_msg)
                return {"error": error_msg}
            
            # 如果有匹配的七日預報資料，記錄天氣元素的詳細資訊
            if forecast_type != "36h" and location and "Locations" in data["records"] and isinstance(data["records"]["Locations"], list):
                try:
                    # 建立可能的地點名稱變體
                    location_variants = [location]
                    if '臺' in location:
                        location_variants.append(location.replace('臺', '台'))
                    elif '台' in location:
                        location_variants.append(location.replace('台', '臺'))
                    
                    # 如果沒有包含「市」或「縣」，嘗試添加
                    if not any(x in location for x in ['市', '縣']):
                        location_variants.extend([f"{loc}市" for loc in location_variants])
                        location_variants.extend([f"{loc}縣" for loc in location_variants])
                    
                    # 記錄嘗試匹配的變體
                    api_logger.info(f"嘗試匹配的地點變體: {location_variants}")
                    
                    # 尋找匹配的地點
                    matched_locations = []
                    available_locations = []
                    
                    for loc_group in data["records"]["Locations"]:
                        if "Location" in loc_group:
                            for loc in loc_group["Location"]:
                                loc_name = loc.get("LocationName", "")
                                available_locations.append(loc_name)
                                
                                # 檢查是否有任何變體匹配
                                for variant in location_variants:
                                    # 完全匹配
                                    if variant == loc_name:
                                        matched_locations.append(loc)
                                        api_logger.info(f"找到完全匹配地點 '{variant}' 的七日預報資料: [{loc_name}]")
                                        break
                    
                    # 如果沒有找到完全匹配，嘗試部分匹配
                    if not matched_locations:
                        for loc_group in data["records"]["Locations"]:
                            if "Location" in loc_group:
                                for loc in loc_group["Location"]:
                                    loc_name = loc.get("LocationName", "")
                                    
                                    # 檢查是否有任何變體匹配
                                    for variant in location_variants:
                                        if variant in loc_name or loc_name in variant:
                                            matched_locations.append(loc)
                                            api_logger.info(f"找到部分匹配地點 '{variant}' 的七日預報資料: [{loc_name}]")
                                            break
                    
                    if not matched_locations:
                        error_msg = f"找不到 {location} 的天氣預報資料"
                        logger.warning(error_msg)
                        api_logger.warning(error_msg)
                        
                        # 記錄可用的地點名稱，以便除錯
                        api_logger.info(f"可用的地點名稱（前10個）: {available_locations[:10]}")
                        
                        # 如果是「台北市」，嘗試直接使用「臺北市」
                        if location == "台北市":
                            api_logger.info("嘗試使用「臺北市」代替「台北市」")
                            for loc_group in data["records"]["Locations"]:
                                if "Location" in loc_group:
                                    for loc in loc_group["Location"]:
                                        if loc.get("LocationName", "") == "臺北市":
                                            matched_locations.append(loc)
                                            api_logger.info(f"找到臺北市的七日預報資料")
                                            break
                        
                        if not matched_locations:
                            return {"error": error_msg}
                    
                    api_logger.info(f"找到 {len(matched_locations)} 個匹配的地點預報資料")
                    
                    # 記錄天氣元素資訊
                    for loc in matched_locations:
                        loc_name = loc.get("LocationName", "未知")
                        api_logger.info(f"記錄 {loc_name} 的天氣預報資料")
                        
                        if "WeatherElement" not in loc:
                            continue
                            
                        weather_elements = loc["WeatherElement"]
                        api_logger.info(f"找到 {len(weather_elements)} 個天氣元素")
                        
                        # 建立結構化的預報資料
                        parsed_forecast = {
                            "location": loc_name,
                            "forecasts": []
                        }

                        # 記錄溫度和天氣現象
                        for elem in weather_elements:
                            elem_name = elem.get("ElementName", "未知")
                            
                            # 只記錄重要的天氣元素
                            if elem_name in ["最高溫度", "最低溫度", "天氣現象", "12小時降雨機率"]:
                                if "Time" in elem and elem["Time"]:
                                    for time_data in elem["Time"]:
                                        start_time = time_data.get("StartTime", "未知")
                                        end_time = time_data.get("EndTime", "未知")
                                        element_value = time_data.get("ElementValue", [])
                                        
                                        # 找到或建立對應時間段的預報資料
                                        forecast_entry = None
                                        for entry in parsed_forecast["forecasts"]:
                                            if entry["start_time"] == start_time and entry["end_time"] == end_time:
                                                forecast_entry = entry
                                                break
                                        
                                        if forecast_entry is None:
                                            forecast_entry = {
                                                "start_time": start_time,
                                                "end_time": end_time,
                                                "max_temperature": None,
                                                "min_temperature": None,
                                                "weather": None,
                                                "weather_code": None,
                                                "precipitation_probability": None
                                            }
                                            parsed_forecast["forecasts"].append(forecast_entry)
                                        
                                        if element_value and isinstance(element_value, list) and len(element_value) > 0:
                                            # 根據元素類型更新預報資料
                                            if elem_name == "最高溫度":
                                                value = element_value[0].get("MaxTemperature", "未知")
                                                try:
                                                    if value != "未知" and value != "-":
                                                        forecast_entry["max_temperature"] = float(value)
                                                        api_logger.info(f"  {start_time} 至 {end_time}: 最高溫度 {value}°C")
                                                    else:
                                                        forecast_entry["max_temperature"] = None
                                                except (ValueError, TypeError):
                                                    forecast_entry["max_temperature"] = None
                                                    api_logger.warning(f"  無法解析最高溫度值: {value}")
                                            
                                            elif elem_name == "最低溫度":
                                                value = element_value[0].get("MinTemperature", "未知")
                                                try:
                                                    if value != "未知" and value != "-":
                                                        forecast_entry["min_temperature"] = float(value)
                                                        api_logger.info(f"  {start_time} 至 {end_time}: 最低溫度 {value}°C")
                                                    else:
                                                        forecast_entry["min_temperature"] = None
                                                except (ValueError, TypeError):
                                                    forecast_entry["min_temperature"] = None
                                                    api_logger.warning(f"  無法解析最低溫度值: {value}")
                                            
                                            elif elem_name == "天氣現象":
                                                weather = element_value[0].get("Weather", "未知")
                                                weather_code = element_value[0].get("WeatherCode", "未知")
                                                forecast_entry["weather"] = weather if weather != "未知" else None
                                                forecast_entry["weather_code"] = weather_code if weather_code != "未知" else None
                                                if forecast_entry["weather"]:
                                                    api_logger.info(f"  {start_time} 至 {end_time}: 天氣現象 {weather}")
                                                else:
                                                    api_logger.info(f"  {start_time} 至 {end_time}: 天氣現象 未知")
                                            
                                            elif elem_name == "12小時降雨機率":
                                                value = element_value[0].get("ProbabilityOfPrecipitation", "未知")
                                                try:
                                                    if value != "未知" and value != "-":
                                                        prob = float(value)
                                                        # Ensure probability is between 0 and 100
                                                        forecast_entry["precipitation_probability"] = max(0, min(100, prob))
                                                        api_logger.info(f"  {start_time} 至 {end_time}: 降雨機率 {value}%")
                                                    else:
                                                        forecast_entry["precipitation_probability"] = None
                                                        api_logger.info(f"  {start_time} 至 {end_time}: 降雨機率 未知")
                                                except (ValueError, TypeError):
                                                    forecast_entry["precipitation_probability"] = None
                                                    api_logger.warning(f"  無法解析降雨機率值: {value}")

                        # 將解析後的資料加入到回傳結果中
                        if "parsed_forecasts" not in data:
                            data["parsed_forecasts"] = []
                        data["parsed_forecasts"].append(parsed_forecast)
                        
                        api_logger.info(f"  ... (共 {len(parsed_forecast['forecasts'])} 筆預報資料)")
                        
                except Exception as e:
                    api_logger.error(f"記錄七日預報天氣元素時發生錯誤: {str(e)}")
                    return {"error": f"處理七日預報資料時發生錯誤: {str(e)}"}
            
            return data
            
        except Exception as e:
            logger.error(f"取得天氣預報時發生錯誤: {str(e)}")
            return {"error": str(e)}
    
    async def get_weather_warnings(self, hazard_type: str = None, location: str = None) -> Dict[str, Any]:
        """取得天氣警特報資料。
        
        Args:
            hazard_type: 可選的災害類型過濾條件 (例如: 濃霧, 大雨, 豪雨)
            location: 可選的地點名稱過濾條件 (例如: 臺北市, 高雄市)
        
        Returns:
            Dict[str, Any]: 包含警特報資料的字典，如有錯誤則包含 'error' 欄位
        """
        params = {
            "format": "JSON"
        }
        
        # 處理災害類型參數 (如果指定)
        if hazard_type:
            hazard_type = hazard_type.strip()
            params["phenomena"] = hazard_type
            logger.info(f"獲取天氣警特報，災害類型: {hazard_type}")
        
        # 處理地點參數 (如果指定)
        if location:
            location = location.strip()
            params["locationName"] = location
            logger.info(f"獲取天氣警特報，地點: {location}")
        else:
            logger.info("獲取全部地區天氣警特報")
        
        endpoint = "W-C0033-001"
        logger.info(f"獲取天氣警特報，使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            # 檢查API回應是否有錯誤
            if "error" in data:
                logger.error(f"API返回錯誤: {data['error']}")
                return data
                
            # 檢查API回應是否包含必要的資料結構
            if "records" not in data:
                logger.error("警特報回應中缺少 records 欄位")
                return {"error": "無效的 API 回應: 缺少 records 欄位"}
            
            # 檢查是否有警特報資料
            # 首先檢查 location 欄位 (新版 API 格式)
            if "location" in data["records"]:
                locations = data["records"]["location"]
                warnings_count = 0
                
                # 記錄找到的警特報資訊
                for i, loc in enumerate(locations[:5]):
                    loc_name = loc.get("locationName", "未知")
                    
                    # 檢查是否有災害條件
                    if "hazardConditions" in loc and "hazards" in loc["hazardConditions"]:
                        hazards = loc["hazardConditions"]["hazards"]
                        if hazards:
                            warnings_count += len(hazards)
                            
                            # 記錄前幾筆警特報的基本資訊
                            for j, hazard in enumerate(hazards[:2]):
                                if "info" in hazard:
                                    hazard_info = hazard["info"]
                                    phenomena = hazard_info.get("phenomena", "未知")
                                    significance = hazard_info.get("significance", "未知")
                                    start_time = hazard_info.get("startTime", "未知")
                                    end_time = hazard_info.get("endTime", "未知")
                                    logger.info(f"警特報 {i+1}-{j+1}: {phenomena} ({significance}) - 地區: {loc_name}, 時間: {start_time} 至 {end_time}")
                
                logger.info(f"找到 {warnings_count} 筆警特報資料")
                
                # 為了保持與舊版 API 相容，將 location 資料轉換為 record 格式
                if "record" not in data["records"]:
                    data["records"]["record"] = []
                    
                    # 將每個地點的災害資訊轉換為獨立的警特報記錄
                    for loc in locations:
                        loc_name = loc.get("locationName", "未知")
                        
                        if "hazardConditions" in loc and "hazards" in loc["hazardConditions"]:
                            hazards = loc["hazardConditions"]["hazards"]
                            for hazard in hazards:
                                if "info" in hazard:
                                    warning_record = {
                                        "locationName": [loc_name],
                                        "phenomena": hazard["info"].get("phenomena", "未知"),
                                        "significance": hazard["info"].get("significance", "未知"),
                                        "validTime": {
                                            "startTime": hazard["validTime"].get("startTime", "未知"),
                                            "endTime": hazard["validTime"].get("endTime", "未知")
                                        }
                                    }
                                    data["records"]["record"].append(warning_record)
                
                if warnings_count == 0:
                    logger.info("目前無警特報資料")
            # 檢查 record 欄位 (舊版 API 格式)
            elif "record" in data["records"]:
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
                logger.warning("警特報回應中缺少 location 或 record 欄位")
                data["records"]["record"] = []  # 確保回應中有 record 欄位，即使它是空的
                
            return data
        except Exception as e:
            logger.error(f"取得天氣警特報時發生錯誤: {str(e)}")
            return {"error": f"取得天氣警特報時發生錯誤: {str(e)}"}
    
    async def get_rainfall_data(self, location: str = None) -> Dict[str, Any]:
        """Get rainfall observation data.
        
        Args:
            location: Optional location name to filter results
            
        Returns:
            Rainfall observation data
        """
        params = {}
        if location:
            # 使用 CountyName 參數來過濾縣市
            params["CountyName"] = location.strip()
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
            
            # 檢查 API 回應中的資料結構
            records = data["records"]
            
            # 將原始資料結構轉換為標準化的格式
            # 創建一個新的資料結構，包含 location 欄位
            standardized_data = {
                "success": data.get("success", "true"),
                "records": {
                    "location": []
                }
            }
            
            # 從 API 回應中提取站點資料
            if "Station" in records:
                stations = records["Station"]
                for station in stations:
                    # 創建標準化的地點資料
                    location_data = {
                        "locationName": station.get("CountyName", ""),
                        "time": {
                            "obsTime": station.get("ObsTime", {}).get("DateTime", "")
                        },
                        "weatherElement": []
                    }
                    
                    # 提取雨量資料
                    if "RainfallElement" in station:
                        rainfall = station["RainfallElement"]
                        for element_name, element_value in rainfall.items():
                            # 跳過非數值欄位
                            if element_name in ["RecordTime", "Status"]:
                                continue
                                
                            # 添加雨量元素
                            location_data["weatherElement"].append({
                                "elementName": element_name,
                                "elementValue": element_value
                            })
                    
                    # 添加地點資料到標準化結構
                    standardized_data["records"]["location"].append(location_data)
                
                logger.info(f"成功標準化 {len(standardized_data['records']['location'])} 個雨量觀測站點資料")
                return standardized_data
            else:
                logger.warning("API 回應中未找到 Station 欄位")
                # 返回原始資料，讓伺服器處理
                return data
        except Exception as e:
            logger.error(f"取得雨量資料時發生錯誤: {str(e)}")
            return {"error": str(e)}
    
    async def get_weather_observation(self, location: str = None) -> Dict[str, Any]:
        """取得即時氣象觀測資料。
        
        Args:
            location: 可選的地點名稱過濾條件 (例如: 臺北市, 高雄市, 板橋)
            
        Returns:
            Dict[str, Any]: 包含氣象觀測資料的字典，如有錯誤則包含 'error' 欄位
        """
        params = {
            "format": "JSON"
        }
        
        # 不在 API 請求時設定縣市別，而是獲取所有資料後再過濾
        if location:
            location = location.strip()
            logger.info(f"獲取氣象觀測資料，準備過濾地點: {location}")
        else:
            logger.info("獲取全部氣象觀測資料")
            
        endpoint = "O-A0003-001"
        logger.info(f"使用端點: {endpoint}，參數: {params}")
        
        try:
            data = await self._make_request(endpoint, params)
            
            # 檢查API回應是否有錯誤
            if "error" in data:
                logger.error(f"API返回錯誤: {data['error']}")
                return data
                
            # 檢查API回應是否包含必要的資料結構
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
                
                # 建立可能的地點名稱變體
                location_variants = []
                if location:
                    location_variants = [location]
                    if '臺' in location:
                        location_variants.append(location.replace('臺', '台'))
                    elif '台' in location:
                        location_variants.append(location.replace('台', '臺'))
                    
                    # 如果沒有包含「市」或「縣」，嘗試添加
                    if not any(x in location for x in ['市', '縣']):
                        location_variants.extend([f"{loc}市" for loc in location_variants])
                        location_variants.extend([f"{loc}縣" for loc in location_variants])
                    
                    logger.info(f"嘗試匹配的地點名稱變體: {location_variants}")
                
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
                        match_found = False
                        
                        # 檢查各種地點名稱變體
                        for variant in location_variants:
                            variant_lower = variant.lower()
                            county_lower = county_name.lower()
                            town_lower = town_name.lower()
                            station_lower = station_name.lower()
                            full_location_lower = full_location_name.lower()
                            
                            # 優先檢查縣市名稱是否匹配
                            if variant_lower == county_lower or county_lower in variant_lower or variant_lower in county_lower:
                                match_found = True
                                logger.info(f"找到縣市匹配的觀測站: {full_location_name} (搜尋: {variant}, 縣市: {county_name})")
                                break
                            
                            # 其次檢查區域名稱是否匹配
                            if variant_lower == town_lower or town_lower in variant_lower or variant_lower in town_lower:
                                match_found = True
                                logger.info(f"找到區域匹配的觀測站: {full_location_name} (搜尋: {variant}, 區域: {town_name})")
                                break
                            
                            # 最後檢查觀測站名稱是否匹配
                            if variant_lower == station_lower or station_lower in variant_lower or variant_lower in station_lower:
                                match_found = True
                                logger.info(f"找到觀測站名稱匹配的觀測站: {full_location_name} (搜尋: {variant}, 觀測站: {station_name})")
                                break
                            
                            # 檢查完整地點名稱是否匹配
                            if variant_lower in full_location_lower:
                                match_found = True
                                logger.info(f"找到完整地點匹配的觀測站: {full_location_name} (搜尋: {variant})")
                                break
                        
                        if not match_found:
                            logger.debug(f"跳過不匹配的觀測站: {full_location_name} (搜尋: {location})")
                            continue
                    
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
                    error_msg = f"未找到匹配地點 '{location}' 的觀測站"
                    logger.warning(error_msg)
                    return {"error": error_msg}
            else:
                error_msg = "回應中缺少 Station 資料"
                logger.error(error_msg)
                return {"error": f"無效的回應: {error_msg}"}
            
            return data
        except Exception as e:
            error_msg = f"取得氣象觀測資料時發生錯誤: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}