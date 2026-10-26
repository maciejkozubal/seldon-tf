# Sourced by 4.1/4.2/4.3. The MODEL axis, decided here because it changes the build context:
#   bake  -> model sits next to the serving code, shipped inside the image (2B)
#   else  -> image carries server code only, step 4 mounts the model from the registry (2A)
rm -rf serving/model
if [ "${1:-}" = bake ]; then
    mkdir -p serving/model
    cp "1_train/$MODEL_FILE" "serving/model/$MODEL_FILE"
    echo "1. model baked into the build context:"
    echo "   serving/model/$MODEL_FILE"
else
    echo "1. model left out of the build context:"
    echo "   mounted at runtime from ${MODEL_FQN:-<unset: run 2a1 or 2a2>}"
fi
