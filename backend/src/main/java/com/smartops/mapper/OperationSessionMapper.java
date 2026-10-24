package com.smartops.mapper;

import com.smartops.entity.OperationSession;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface OperationSessionMapper {
    @Select("SELECT id,user_id,group_id,name,protocol,host,port,username,credential_id,identity_path,jump_session_id,tags_json,description,accent,favorite,status,last_connected_at,created_at,updated_at FROM operation_session WHERE id=#{id} AND user_id=#{userId}")
    OperationSession findById(@Param("id") Long id, @Param("userId") Long userId);

    @Select("SELECT id,user_id,group_id,name,protocol,host,port,username,credential_id,identity_path,jump_session_id,tags_json,description,accent,favorite,status,last_connected_at,created_at,updated_at FROM operation_session WHERE user_id=#{userId} ORDER BY favorite DESC, last_connected_at DESC, name ASC")
    List<OperationSession> findAll(@Param("userId") Long userId);

    @Insert("INSERT INTO operation_session(user_id,group_id,name,protocol,host,port,username,credential_id,identity_path,jump_session_id,tags_json,description,accent,favorite,status) VALUES(#{userId},#{groupId},#{name},#{protocol},#{host},#{port},#{username},#{credentialId},#{identityPath},#{jumpSessionId},#{tagsJson},#{description},#{accent},#{favorite},#{status})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(OperationSession session);

    @Delete("DELETE FROM operation_session WHERE id=#{id} AND user_id=#{userId}")
    int delete(@Param("id") Long id, @Param("userId") Long userId);
}
