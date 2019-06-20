import torch
import numpy as np
import mmcv

def reduce_vision(x,mask_size):
    quater_size = mask_size // 4
    base = ((0,quater_size*2),(quater_size,quater_size*3),(quater_size*2,quater_size*4))
    layers = [x[:,i:i+1][:,:,base[i%3][0]:base[i%3][1],base[i//3][0]:base[i//3][1]] for i in range(9)]
    layers = torch.cat(layers,dim=1)
    return layers

def grid_target(sampling_results,cfg):
    #We don't care about image_idx and mix all samples(across images) together.
    pos_bboxes = torch.cat([res.pos_bboxes for res in sampling_results],dim=0)
    pos_gt_bboxes = torch.cat([res.pos_gt_bboxes for res in sampling_results],dim=0)
    assert(pos_bboxes.shape == pos_gt_bboxes.shape)
    device = pos_bboxes.device
    #expand pos_bboxes
    x1 = pos_bboxes[:,0] - (pos_bboxes[:,2] - pos_bboxes[:,0]) / 2
    y1 = pos_bboxes[:,1] - (pos_bboxes[:,3] - pos_bboxes[:,1]) / 2
    x2 = pos_bboxes[:,2] + (pos_bboxes[:,2] - pos_bboxes[:,0]) / 2
    y2 = pos_bboxes[:,3] + (pos_bboxes[:,3] - pos_bboxes[:,1]) / 2
    
    pos_bboxes = torch.cat(list(map(lambda x:x.view(-1,1),[x1,y1,x2,y2])),dim=1)

    R = pos_bboxes.shape[0]
    G = cfg.num_grids
    mask_size = cfg.mask_size
    targets = np.zeros([R,G,mask_size,mask_size])

    for rix in range(R):
        for gix in range(G):
            gridpoint_x = (1-gix//3/2)*(pos_gt_bboxes[rix,0]) + (gix//3/2)*(pos_gt_bboxes[rix,2])
            gridpoint_y = (1-gix%3/2)*(pos_gt_bboxes[rix,1]) + (gix%3/2)*(pos_gt_bboxes[rix,3])
            if (pos_bboxes[rix,2] - pos_bboxes[rix,0]) < 4 or (pos_bboxes[rix,3] - pos_bboxes[rix,1]) < 4:
                continue
            cx = int((gridpoint_x - pos_bboxes[rix,0])/(pos_bboxes[rix,2] - pos_bboxes[rix,0])*mask_size)
            cy = int((gridpoint_y - pos_bboxes[rix,1])/(pos_bboxes[rix,3] - pos_bboxes[rix,1])*mask_size)
            radius = cfg.get('radius',1)
            for x in range(cx - radius,cx + radius + 1):
                for y in range(cy - radius, cy + radius + 1):
                    if x >= 0 and x < mask_size and y>=0 and y < mask_size and (x-cx)**2+(y-cy)**2<=radius**2:
                        targets[rix,gix,y,x] = 1
    targets = torch.Tensor(targets).to(device=device)
    targets = reduce_vision(targets,mask_size)

    return targets

### radom jittering
def random_jitter_single(sampling_results,img_meta,amplitude=0.15):    
    rois = sampling_results.pos_bboxes.cpu()
    R,K = rois.shape
    random_offset = torch.FloatTensor(R,4).uniform_(-amplitude,amplitude)
    #before jittering
    ctx_ = (rois[:,2] + rois[:,0])/2
    cty_ = (rois[:,1] + rois[:,3])/2
    width_ = (rois[:,2] - rois[:,0]).abs()
    height_ = (rois[:,3] - rois[:,1]).abs()
    #after jittering
    ctx = ctx_ + random_offset[:,0] * width_
    cty = cty_ + random_offset[:,1] * height_
    width = width_ * (1 + random_offset[:,2])
    height = height_ * (1 + random_offset[:,3])

    x1 = (ctx - width/2).view(-1,1)
    y1 = (cty - height/2).view(-1,1)
    x2 = (ctx + width/2).view(-1,1)
    y2 = (cty + height/2).view(-1,1)

    max_shape = img_meta['img_shape']
    if max_shape is not None:
        x1 = x1.clamp(min=0, max=max_shape[1] - 1)
        y1 = y1.clamp(min=0, max=max_shape[0] - 1)
        x2 = x2.clamp(min=0, max=max_shape[1] - 1)
        y2 = y2.clamp(min=0, max=max_shape[0] - 1)

    rois = torch.cat([x1,y1,x2,y2],dim=1).cuda()
    sampling_results.pos_bboxes = rois
    return sampling_results

def random_jitter(sampling_results,img_metas):
    post_sampling_results = map(random_jitter_single,sampling_results,img_metas)
    return list(post_sampling_results)