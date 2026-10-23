// Synthetic regression: copy a 3x4 transform through a ray payload.
struct Payload {
    float3x4 transform;
    float3 color;
};
[shader("closesthit")]
void MatrixClosestHit(inout Payload payload, BuiltInTriangleIntersectionAttributes hit) {
    payload.transform = ObjectToWorld3x4();
    payload.color = mul(payload.transform, float4(hit.barycentrics, 1.0, 1.0));
}
[shader("miss")]
void MatrixMiss(inout Payload payload) {
    payload.transform[0][0] += 1.0;
}
