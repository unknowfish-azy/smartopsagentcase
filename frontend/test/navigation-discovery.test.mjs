import test from 'node:test'
import assert from 'node:assert/strict'
import { navigationEntries, searchEntries, restoreTabPaths, restoreRecentPaths, rememberRecentPath } from '../src/navigation/navigationDiscovery.js'
test('navigation index contains permitted groups and children only, without duplicate paths',()=>{
 const entries=navigationEntries([{cn:'模型',label:'MODELS',to:'/models',children:[{cn:'网关',label:'GATEWAY',to:'/gateway'},{cn:'模型',to:'/models'}]}])
 assert.equal(entries.length,2); assert.equal(searchEntries(entries,'网 关')[0].to,'/gateway'); assert.equal(searchEntries(entries,'gate')[0].to,'/gateway'); assert.equal(searchEntries(entries,'账户').length,0)
})
test('restored tabs allow only registered paths and always retain overview',()=>{
 assert.deepEqual(restoreTabPaths('["/admin/users","https://bad","/admin/users"]',{'/admin':'总览','/admin/users':'用户'}),['/admin','/admin/users'])
 assert.deepEqual(restoreTabPaths('broken',{'/admin':'总览'}),['/admin'])
})
test('recent navigation keeps only registered paths, newest first, capped at five',()=>{
 const entries=[{to:'/a'},{to:'/b'},{to:'/c'},{to:'/d'},{to:'/e'},{to:'/f'}]
 assert.deepEqual(restoreRecentPaths('["/x","/b","/b","/a"]',entries),['/b','/a'])
 assert.deepEqual(JSON.parse(rememberRecentPath('["/b","/a"]','/c',entries)),['/c','/b','/a'])
})
