# PRG 2.7 文件格式参考

## 容器
`.prg` 是 ZIP archive。

核心条目：
- `stage.msgpack`
- `tags.msgpack`
- `reference.msgpack`
- `metadata.msgpack`

可选：
- `README.md`
- `attachments/...`
- `thumbnail.png`

建议 ZIP payload 使用 STORE / compression level 0。

## metadata
```python
{"version": "2.7.0"}
```

## 引用
序列化对象使用：
```python
{"$": "/<stage-index>"}
```
指向 stage 中的对象。

## 基础对象

### Vector
```python
{"_":"Vector","x":0.0,"y":0.0}
```

### Color
```python
{"_":"Color","r":0,"g":0,"b":0,"a":0.0}
```
其中 `a` 范围 0..1。

### Rectangle
```python
{
  "_":"Rectangle",
  "location": Vector,
  "size": Vector
}
```

### CollisionBox
```python
{"_":"CollisionBox","shapes":[Rectangle]}
```

## TextNode
常用字段：
- `_ = TextNode`
- `details`
- `uuid`
- `text`
- `collisionBox`
- `color`
- `fontScaleLevel`
- `sizeAdjust`
- `fontFamily`
- `fontWeight`
- `borderStyle`

## LineEdge
常用字段：
- `_ = LineEdge`
- `associationList`（source, target）
- `sourceRectangleRate`
- `targetRectangleRate`
- `uuid`
- `text`
- `color`
- `lineType`
- `arrowType`

## ArcEdge
在 LineEdge 语义基础上增加：
- `offset`
- `textPosition`

## MultiTargetUndirectedEdge
常用字段：
- `associationList`
- `rectRates`
- `centerRate`
- `arrow`
- `arrowType`
- `renderType`
- `lineType`
- `padding`
- `text`
- `color`

## Section
常用字段：
- `details`
- `uuid`
- `color`
- `text`
- `children`
- `isCollapsed`
- `locked`
- `borderStyle`

## SyncAssociation
常用字段：
- `uuid`
- `keys`
- `associationList`

## ReferenceBlockNode
常用字段：
- `details`
- `uuid`
- `collisionBox`
- `fileName`
- `sectionName`
- `scale`
- `attachmentId`

## 重要工程原则
不要仅凭版本号假设复杂对象一定正确。每次新增原语都应该通过最小 probe 或真实文件验证。
