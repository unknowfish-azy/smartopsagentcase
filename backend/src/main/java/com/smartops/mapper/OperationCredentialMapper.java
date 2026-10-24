package com.smartops.mapper;

import com.smartops.entity.OperationCredential;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface OperationCredentialMapper {
    @Select("SELECT id,user_id,name,type,secret_ciphertext,last4,created_at,updated_at FROM operation_credential WHERE id=#{id} AND user_id=#{userId}")
    OperationCredential findById(@Param("id") Long id, @Param("userId") Long userId);

    @Insert("INSERT INTO operation_credential(user_id,name,type,secret_ciphertext,last4) VALUES(#{userId},#{name},#{type},#{secretCiphertext},#{last4})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(OperationCredential credential);
}
