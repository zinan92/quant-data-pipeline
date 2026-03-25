"""
Test suite for index_updater service
Verifies INDEX_LIST configuration and CSI indices addition
"""

from src.services.index_updater import INDEX_LIST


class TestIndexListConfiguration:
    """Test INDEX_LIST has correct structure and content"""

    def test_index_list_has_8_entries(self):
        """Verify INDEX_LIST contains exactly 8 indices"""
        assert len(INDEX_LIST) == 8, f"Expected 8 indices, got {len(INDEX_LIST)}"

    def test_index_list_format_is_3_tuple(self):
        """Verify each INDEX_LIST entry is a 3-tuple (ts_code, sina_code, name)"""
        for entry in INDEX_LIST:
            assert isinstance(entry, tuple), f"Entry {entry} is not a tuple"
            assert len(entry) == 3, f"Entry {entry} should have 3 elements, has {len(entry)}"
            ts_code, sina_code, name = entry
            assert isinstance(ts_code, str), f"ts_code should be string, got {type(ts_code)}"
            assert isinstance(sina_code, str), f"sina_code should be string, got {type(sina_code)}"
            assert isinstance(name, str), f"name should be string, got {type(name)}"

    def test_original_5_indices_present(self):
        """Verify original 5 indices are preserved"""
        ts_codes = [entry[0] for entry in INDEX_LIST]
        
        expected_original = [
            "000001.SH",  # 上证指数
            "399001.SZ",  # 深证成指
            "399006.SZ",  # 创业板指
            "000688.SH",  # 科创50
            "899050.BJ",  # 北证50
        ]
        
        for code in expected_original:
            assert code in ts_codes, f"Original index {code} missing from INDEX_LIST"

    def test_csi_300_present(self):
        """Verify CSI 300 (000300.SH) is in INDEX_LIST"""
        ts_codes = [entry[0] for entry in INDEX_LIST]
        assert "000300.SH" in ts_codes, "CSI 300 (000300.SH) missing from INDEX_LIST"
        
        # Find the entry and verify full details
        csi300 = next((entry for entry in INDEX_LIST if entry[0] == "000300.SH"), None)
        assert csi300 is not None
        assert csi300[1] == "sh000300", f"CSI 300 sina_code should be 'sh000300', got {csi300[1]}"
        assert csi300[2] == "沪深300", f"CSI 300 name should be '沪深300', got {csi300[2]}"

    def test_csi_500_present(self):
        """Verify CSI 500 (000905.SH) is in INDEX_LIST"""
        ts_codes = [entry[0] for entry in INDEX_LIST]
        assert "000905.SH" in ts_codes, "CSI 500 (000905.SH) missing from INDEX_LIST"
        
        # Find the entry and verify full details
        csi500 = next((entry for entry in INDEX_LIST if entry[0] == "000905.SH"), None)
        assert csi500 is not None
        assert csi500[1] == "sh000905", f"CSI 500 sina_code should be 'sh000905', got {csi500[1]}"
        assert csi500[2] == "中证500", f"CSI 500 name should be '中证500', got {csi500[2]}"

    def test_csi_1000_present(self):
        """Verify CSI 1000 (000852.SH) is in INDEX_LIST"""
        ts_codes = [entry[0] for entry in INDEX_LIST]
        assert "000852.SH" in ts_codes, "CSI 1000 (000852.SH) missing from INDEX_LIST"
        
        # Find the entry and verify full details
        csi1000 = next((entry for entry in INDEX_LIST if entry[0] == "000852.SH"), None)
        assert csi1000 is not None
        assert csi1000[1] == "sh000852", f"CSI 1000 sina_code should be 'sh000852', got {csi1000[1]}"
        assert csi1000[2] == "中证1000", f"CSI 1000 name should be '中证1000', got {csi1000[2]}"

    def test_sina_code_format_correct(self):
        """Verify all sina_codes use correct prefix format"""
        for ts_code, sina_code, name in INDEX_LIST:
            code, market = ts_code.split(".")
            
            if market == "SH":
                expected_prefix = "sh"
            elif market == "SZ":
                expected_prefix = "sz"
            elif market == "BJ":
                expected_prefix = "bj"
            else:
                assert False, f"Unknown market {market} for {ts_code}"
            
            assert sina_code.startswith(expected_prefix), \
                f"Sina code {sina_code} should start with {expected_prefix} for {ts_code}"
            assert sina_code == f"{expected_prefix}{code}", \
                f"Sina code {sina_code} should be {expected_prefix}{code}"

    def test_all_three_csi_indices_present(self):
        """Verify all three CSI indices (300, 500, 1000) are in INDEX_LIST"""
        ts_codes = [entry[0] for entry in INDEX_LIST]
        
        expected_csi = ["000300.SH", "000905.SH", "000852.SH"]
        for code in expected_csi:
            assert code in ts_codes, f"CSI index {code} missing from INDEX_LIST"

    def test_no_duplicate_ts_codes(self):
        """Verify no duplicate ts_codes in INDEX_LIST"""
        ts_codes = [entry[0] for entry in INDEX_LIST]
        assert len(ts_codes) == len(set(ts_codes)), "Duplicate ts_codes found in INDEX_LIST"

    def test_no_duplicate_sina_codes(self):
        """Verify no duplicate sina_codes in INDEX_LIST"""
        sina_codes = [entry[1] for entry in INDEX_LIST]
        assert len(sina_codes) == len(set(sina_codes)), "Duplicate sina_codes found in INDEX_LIST"
