import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import numpy as np
import io
import re

# --- 설정값 (CAN 데이터 변환 상수) ---
TARGET_CAN_ID = '295'      
START_BYTE_INDEX = 1       
MAX_PHYSICAL_PRESSURE = 200.0 
PHYSICAL_FACTOR = MAX_PHYSICAL_PRESSURE / 255.0 

# 🚨 [수정] 그래프 Y축 최대 범위만 250.0 bar로 변경
MAX_PLOT_Y_BAR = 250.0     
HEADER_ROWS_TO_SKIP = 5    

COLUMNS = ['Bus', 'No', 'Time', 'State', 'ID (hex)', 'DLC', 'Data (hex)', 'ASCII']
TIME_COLUMN = 'Time'
CAN_ID_COLUMN = 'ID (hex)'
DATA_COLUMN = 'Data (hex)' 

GRAPH_COLORS = ['r', 'b', 'g'] # 빨간색, 파란색, 초록색
LINE_WIDTH = 1.0               # 얇은 두께

# --- 함수 정의 ---

def hex_to_pressure(hex_data_string):
    """
    CAN 데이터 페이로드에서 Start Byte (1)의 값을 추출하여 0-200 bar 물리적 계수를 적용해 변환합니다.
    """
    try:
        byte_list = hex_data_string.strip().split()
        data_byte_hex = byte_list[START_BYTE_INDEX] 
        decimal_value = int(data_byte_hex, 16)
        
        # 물리적 최대 압력 (200 bar)에 맞춘 계수 적용 (0-255 -> 0-200 bar)
        pressure = decimal_value * PHYSICAL_FACTOR
        
        return pressure
        
    except (IndexError, ValueError):
        return np.nan 

@st.cache_data
def load_and_process_data(uploaded_file, file_index):
    """
    업로드된 CSV 파일을 읽고 압력 데이터로 변환 및 필터링합니다.
    """
    st.info(f"파일 {file_index} ({uploaded_file.name}) 처리 중...")
    
    delimiters = [',', '\\s+', '\t', ';']
    df = None
    
    # 1. 파일 로드 시도
    for sep in delimiters:
        try:
            data = uploaded_file.getvalue().decode("utf-8")
            df = pd.read_csv(
                io.StringIO(data), 
                sep=sep, 
                header=None,             
                names=COLUMNS,           
                skiprows=HEADER_ROWS_TO_SKIP, 
                engine='python'          
            )
            
            if all(col in df.columns for col in [TIME_COLUMN, CAN_ID_COLUMN, DATA_COLUMN]):
                st.success(f"파일 {file_index} ({uploaded_file.name})를 **'{sep}'** 구분자로 성공적으로 로드했습니다.")
                break
            else:
                df = None
                continue 
        except Exception:
            df = None
            continue
    
    if df is None:
        st.error(f"⚠️ 파일 {file_index} 오류: 데이터를 로드할 수 없습니다. 파일 형식 및 인코딩을 확인하거나, 상단 헤더 줄 수({HEADER_ROWS_TO_SKIP}줄)를 확인하세요.")
        return None

    try:
        df_filtered = df.copy()

        # 2. 대상 CAN ID (0x295) 필터링 및 방어적 인덱싱
        df_filtered.loc[:, CAN_ID_COLUMN] = df_filtered[CAN_ID_COLUMN].astype(str).str.strip().str.upper()
        df_filtered = df_filtered[df_filtered[CAN_ID_COLUMN] == TARGET_CAN_ID].copy() 
        df_filtered.reset_index(drop=True, inplace=True) 

        if df_filtered.empty:
            st.warning(f"파일 {file_index}: CAN ID '{TARGET_CAN_ID}'에 해당하는 데이터가 없어 그래프를 그릴 수 없습니다.")
            return None
        
        # 3. 시간 변환 (Pandas 네이티브 로직)
        time_series = df_filtered[TIME_COLUMN].astype(str).str.strip()
        
        try:
            time_dt_str = time_series.str.replace(r'(\d+):(\d+\.?\d*)', r'00:\1:\2', regex=True)
            time_dt = pd.to_datetime(time_dt_str, format='%H:%M:%S.%f', errors='coerce')
            
            time_delta = time_dt - time_dt.min()
            df_filtered.loc[:, TIME_COLUMN] = time_delta.dt.total_seconds()
            
        except Exception as e:
             st.error(f"⚠️ 파일 {file_index} 시간 변환 중 오류 발생: {e}. Time 컬럼 형식(분:초.ms) 확인 필요.")
             df_filtered.loc[:, TIME_COLUMN] = np.nan 

        # 4. 압력 계산
        df_filtered.loc[:, DATA_COLUMN] = df_filtered[DATA_COLUMN].astype(str).str.strip()
        df_filtered.loc[:, 'Pressure'] = df_filtered[DATA_COLUMN].apply(hex_to_pressure)
        
        # 5. NaN 값 제거
        df_filtered.dropna(subset=['Pressure', TIME_COLUMN], inplace=True)

        if df_filtered.empty:
            st.error(f"파일 {file_index}: 데이터는 로드되었으나, **변환 후 유효한 데이터가 남아있지 않아** 그래프를 그릴 수 없습니다.")
            return None
            
        return df_filtered
    except Exception as e:
        st.error(f"⚠️ 파일 {file_index} 데이터 필터링/변환 중 오류 발생: {e}")
        return None

# --- Streamlit 앱 메인 로직 ---

st.set_page_config(layout="wide", page_title="CAN 압력 그래프 분석기")
st.title("📊 CAN 데이터 압력 그래프 분석기")
st.markdown(f"최대 3개의 CSV 파일을 업로드하여 **CAN ID {TARGET_CAN_ID}**의 그래프를 확인하고 비교할 수 있습니다.")

# 파일 업로드 위젯 (최대 3개)
uploaded_files = st.file_uploader(
    "CAN 데이터 CSV 파일을 업로드하세요 (최대 3개)", 
    type=['csv'], 
    accept_multiple_files=True
)

if uploaded_files:
    files_to_process = uploaded_files[:3] 
    
    processed_data = {}
    for i, file in enumerate(files_to_process):
        df = load_and_process_data(file, i + 1)
        if df is not None and not df.empty:
            processed_data[i] = {
                'df': df, 
                'name': file.name
            }

    if processed_data:
        st.header("개별 그래프 및 축 설정")
        
        tab_titles = []
        all_dfs = []

        for i, (idx, data) in enumerate(processed_data.items()):
            cleaned_name = data['name'].replace('.csv', '')
            tab_titles.append(f"Graph {i+1}: {cleaned_name}")
            all_dfs.append({'df': data['df'], 'name': data['name'], 'cleaned_name': cleaned_name})
        
        tab_titles.append("중첩 비교")
        tabs = st.tabs(tab_titles)
        
        
        # --- 개별 그래프 탭 및 설정 ---
        for i, data in enumerate(all_dfs):
            df = data['df']
            name = data['name']
            cleaned_name = data['cleaned_name']
            
            with tabs[i]:
                st.subheader(f"📈 {cleaned_name} - CAN ID {TARGET_CAN_ID}") 
                
                col1, col2 = st.columns(2)
                
                with col1:
                    max_x = df[TIME_COLUMN].max()
                    min_x_default = df[TIME_COLUMN].min()
                    
                    if max_x > min_x_default:
                        x_range = st.slider(
                            f"File {i+1} X축 범위 (sec)",
                            float(min_x_default), float(max_x), 
                            (float(min_x_default), float(max_x)),
                            step=(max_x - min_x_default) / 100 or 0.01,
                            key=f'x_range_{i}'
                        )
                    else:
                        st.warning("X축 데이터를 사용할 수 없습니다. (데이터 범위 0)")
                        x_range = (min_x_default, max_x)

                with col2:
                    y_range = st.slider(
                        f"File {i+1} Y축 범위 (bar)",
                        0.0, MAX_PLOT_Y_BAR, # 🚨 [수정] 250.0 bar 적용
                        (0.0, MAX_PLOT_Y_BAR),
                        step=0.1,
                        key=f'y_range_{i}'
                    )
                
                if not df.empty:
                    fig, ax = plt.subplots(figsize=(10, 5))
                    
                    color = GRAPH_COLORS[i % len(GRAPH_COLORS)]
                    ax.plot(df[TIME_COLUMN], df['Pressure'], 
                            linewidth=LINE_WIDTH, 
                            color=color)
                    
                    ax.set_title(cleaned_name) 
                    ax.set_xlabel('Time (sec)')
                    ax.set_ylabel('Pressure (bar)') 
                    ax.grid(True)
                    
                    ax.set_xlim(x_range)
                    ax.set_ylim(y_range)
                    
                    st.pyplot(fig)
                    plt.close(fig)

        # --- 중첩 그래프 섹션 (마지막 탭) ---
        
        with tabs[-1]:
            st.header("비교 분석: 중첩 그래프")
            
            st.subheader("표시할 파일 선택")
            
            checkbox_states = {}
            cols = st.columns(len(all_dfs))
            
            for i, data in enumerate(all_dfs):
                with cols[i]:
                    is_checked = st.checkbox(
                        f"파일 {i+1}: {data['cleaned_name']}",
                        value=True, 
                        key=f'overlay_check_{i}'
                    )
                    checkbox_states[i] = is_checked

            
            # 그래프 범위 설정
            if all_dfs:
                
                checked_dfs = [data['df'] for i, data in enumerate(all_dfs) if checkbox_states[i]]
                
                try:
                    max_overall_x = max(d[TIME_COLUMN].max() for d in checked_dfs) if checked_dfs else 0.0
                    min_overall_x = min(d[TIME_COLUMN].min() for d in checked_dfs) if checked_dfs else 0.0
                except ValueError: 
                    max_overall_x = 0.0
                    min_overall_x = 0.0

                col_a, col_b = st.columns(2)
                with col_a:
                    if max_overall_x > min_overall_x:
                        overlay_x_range = st.slider(
                            "중첩 그래프 X축 범위 (sec)",
                            float(min_overall_x), float(max_overall_x), 
                            (float(min_overall_x), float(max_overall_x)),
                            step=(max_overall_x - min_overall_x) / 100 or 0.01,
                            key='overlay_x'
                        )
                    else:
                        st.warning("X축 데이터를 사용할 수 없습니다. (데이터 범위 0)")
                        overlay_x_range = (min_overall_x, max_overall_x)

                with col_b:
                    overlay_y_range = st.slider(
                        "중첩 그래프 Y축 범위 (bar)",
                        0.0, MAX_PLOT_Y_BAR, # 🚨 [수정] 250.0 bar 적용
                        (0.0, MAX_PLOT_Y_BAR),
                        step=0.1,
                        key='overlay_y'
                    )
                
                fig_overlay, ax_overlay = plt.subplots(figsize=(12, 6))
                
                plotted_count = 0
                for i, data in enumerate(all_dfs):
                    if checkbox_states[i]:
                        df = data['df']
                        cleaned_name = data['cleaned_name']
                        color = GRAPH_COLORS[i % len(GRAPH_COLORS)]
                        if not df.empty:
                             ax_overlay.plot(df[TIME_COLUMN], df['Pressure'], 
                                             label=cleaned_name, 
                                             linewidth=LINE_WIDTH, 
                                             color=color)
                             plotted_count += 1
                
                if plotted_count > 0:
                    ax_overlay.set_title(f'Overlayed Pressure vs. Time Comparison (CAN ID {TARGET_CAN_ID})')
                    ax_overlay.set_xlabel('Time (sec)')
                    ax_overlay.set_ylabel('Pressure (bar)')
                    ax_overlay.grid(True)
                    ax_overlay.legend()
                    
                    ax_overlay.set_xlim(overlay_x_range)
                    ax_overlay.set_ylim(overlay_y_range)
                    
                    st.pyplot(fig_overlay)
                    plt.close(fig_overlay)
                else:
                    st.warning("표시할 파일이 선택되지 않았습니다. 하나 이상의 파일을 선택해주세요.")
            else:
                 st.info("처리된 데이터가 없어 중첩 그래프를 표시할 수 없습니다. CAN ID가 0x295인지 확인하세요.")

else:
    st.info("⬆️ 분석을 시작하려면 CSV 파일을 업로드해주세요.")